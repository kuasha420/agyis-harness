#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Tier 3: Cross-Feature Interactions (Issues #41 through #46).
Validates 8 critical cross-feature interactions and subsystem combinations:
- Interaction 1: Scratch Path + Cleanroom Spec Interaction
- Interaction 2: Anti-Loop Exemption + Cleanroom Ledger Verification
- Interaction 3: Anti-Loop Test Reset + Stop-Fence Clearance
- Interaction 4: Cleanroom Edit Failed Test + Scratch Edit Passed Test
- Interaction 5: Doctor Toolchain Audit with REA + Issue Template Correlation
- Interaction 6: Multi-Agent Teamwork Views + Scratch Script Authoring
- Interaction 7: Diverse Universal Test Runner Patterns Recognition
- Interaction 8: Anti-Deadlock Safety Valve Trips on Attempt Three
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import unittest

from harness.delivery.constants import REPO_ROOT
from harness.runtime.doctor import run_doctor
from tests.e2e.harness_base import OpaqueBoxTestCase


class TestTier3Combinations(OpaqueBoxTestCase):
    """
    Tier 3 E2E tests validating cross-feature and multi-subsystem interactions.
    """

    def test_c1_scratch_path_plus_cleanroom_spec_interaction(self) -> None:
        """Assures scratch edits do not mask cleanroom spec verification gates."""
        conv_id = "c_c1"
        scratch_path = "/home/user/.gemini/antigravity/brain/session_1/scratch/calc.py"
        spec_path = str(self.ws / "docs" / "specs" / "display.md")

        # 1. Author scratch script -> clean
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": scratch_path}},
        })
        _, stop1 = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(stop1.get("decision"), "allow")

        # 2. Author cleanroom spec -> dirty
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": spec_path}},
        })
        _, stop2 = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(stop2.get("decision"), "continue")

        # 3. Verify with test -> clean
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "exitCode": 0,
            "toolCall": {"name": "run_command", "args": {"CommandLine": "./agyis test"}},
        })
        _, stop3 = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(stop3.get("decision"), "allow")

    def test_c2_anti_loop_exemption_plus_cleanroom_ledger_verification(self) -> None:
        """Assures viewing ledger is exempt from loop, while editing ledger enforces verification gate."""
        conv_id = "c_c2"
        ledger_path = str(self.ws / ".agents" / "ledger" / "obligations.json")

        # 1. Repeated inspections pass without loop denial
        for _ in range(6):
            code, resp = self.run_hook("anti-loop", {
                "conversationId": conv_id,
                "toolCall": {"name": "view_file", "args": {"AbsolutePath": ledger_path}},
            })
            self.assertEqual(code, 0)
            self.assertEqual(resp.get("decision"), "allow")

        # 2. Edit ledger -> requires verification
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": ledger_path}},
        })
        _, stop = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(stop.get("decision"), "continue")

        # 3. Passing test clears
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "exitCode": 0,
            "toolCall": {"name": "run_command", "args": {"CommandLine": "python3 -m unittest discover"}},
        })
        _, stop_clean = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(stop_clean.get("decision"), "allow")

    def test_c3_anti_loop_test_reset_plus_stop_fence_clearance(self) -> None:
        """Assures code edit resets anti-loop test counters and passing test clears stop-fence."""
        conv_id = "c_c3"
        code_file = str(self.ws / "src" / "router.py")

        # Edit code
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": code_file}},
        })
        self.run_hook("anti-loop", {
            "conversationId": conv_id,
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": code_file}},
        })

        # Anti-loop allows repeated test invocations because code edit reset sliding window
        for _ in range(4):
            code, loop_resp = self.run_hook("anti-loop", {
                "conversationId": conv_id,
                "toolCall": {"name": "run_command", "args": {"CommandLine": "./agyis test"}},
            })
            self.assertEqual(code, 0)
            self.assertEqual(loop_resp.get("decision"), "allow")

        # Stop-fence marks clean on exit 0
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "exitCode": 0,
            "toolCall": {"name": "run_command", "args": {"CommandLine": "./agyis test"}},
        })

        _, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(stop_resp.get("decision"), "allow")

    def test_c4_cleanroom_edit_failed_test_scratch_edit_passed_test(self) -> None:
        """Assures failed test keeps dirty state, scratch edit does not mask it, passed test clears."""
        conv_id = "c_c4"
        spec_path = str(self.ws / "docs" / "specs" / "firmware.md")
        scratch_path = "/tmp/diagnostic_scratch.py"

        # Edit spec
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": spec_path}},
        })

        # Test fails (exit 1)
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "exitCode": 1,
            "toolCall": {"name": "run_command", "args": {"CommandLine": "cargo test"}},
        })

        # Scratch edit in /tmp
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": scratch_path}},
        })

        # Still dirty due to spec edit
        _, stop1 = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(stop1.get("decision"), "continue")

        # Test passes (exit 0)
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "exitCode": 0,
            "toolCall": {"name": "run_command", "args": {"CommandLine": "cargo test"}},
        })

        # Clean
        _, stop2 = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(stop2.get("decision"), "allow")

    def test_c5_doctor_toolchain_audit_with_rea_plus_template_correlation(self) -> None:
        """Assures doctor audit metrics correspond to host_toolchain_versions in issue template."""
        code, out, _ = self.run_cli(["doctor", "--json"])
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertIn("rea_tooling", report)
        self.assertIn("os_family", report)
        self.assertIn("summary", report)

        template_path = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml"
        if template_path.exists():
            tmpl_content = template_path.read_text(encoding="utf-8")
            self.assertIn("host_toolchain_versions", tmpl_content)
            self.assertIn("REA", tmpl_content)

    def test_c6_multi_agent_teamwork_views_plus_scratch_authoring(self) -> None:
        """Assures multi-agent swarm reading teamwork manifests and authoring scratch scripts succeeds."""
        conv_id = "c_c6_swarm"
        manifest1 = str(self.ws / ".agents" / "teamwork" / "DISPATCH.md")
        manifest2 = str(self.ws / ".agents" / "teamwork" / "progress.md")
        scratch = "/home/user/.gemini/antigravity/brain/sess_99/scratch/analyze.py"

        # Agent 1 reads dispatch
        for _ in range(5):
            code, resp = self.run_hook("anti-loop", {
                "conversationId": conv_id,
                "toolCall": {"name": "view_file", "args": {"Path": manifest1}},
            })
            self.assertEqual(code, 0)
            self.assertEqual(resp.get("decision"), "allow")

        # Agent 2 authors scratch
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": scratch}},
        })

        # Agent 1 reads progress
        for _ in range(5):
            code, resp = self.run_hook("anti-loop", {
                "conversationId": conv_id,
                "toolCall": {"name": "view_file", "args": {"Path": manifest2}},
            })
            self.assertEqual(code, 0)
            self.assertEqual(resp.get("decision"), "allow")

        # Stop allowed without test running
        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "allow")

    def test_c7_diverse_test_runner_patterns_recognition(self) -> None:
        """Assures diverse test runners (Python, Cargo, npm, Make, shell) clear dirty state on exit 0."""
        runners = [
            "./agyis test",
            "python3 -m unittest discover",
            "pytest tests/",
            "cargo test",
            "pnpm test",
            "npm test",
            "make test",
            "sh tests/run.sh",
            "bash tests/test_all.sh",
        ]

        for idx, cmd in enumerate(runners):
            conv_id = f"c_c7_{idx}"
            code_file = str(self.ws / "src" / f"mod_{idx}.py")

            # Set dirty
            self.run_hook("verification-fence", {
                "conversationId": conv_id,
                "cwd": str(self.ws),
                "toolCall": {"name": "write_to_file", "args": {"TargetFile": code_file}},
            })

            # Run test command exit 0
            self.run_hook("verification-fence", {
                "conversationId": conv_id,
                "cwd": str(self.ws),
                "exitCode": 0,
                "toolCall": {"name": "run_command", "args": {"CommandLine": cmd}},
            })

            # Verify clean
            code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
            self.assertEqual(code, 0)
            self.assertEqual(
                stop_resp.get("decision"),
                "allow",
                f"Runner command '{cmd}' failed to clear code_dirty state",
            )

    def test_c8_anti_deadlock_valve_trips_on_attempt_three(self) -> None:
        """Assures anti-deadlock safety valve blocks first 2 attempts, then allows exit on attempt 3."""
        conv_id = "c_c8"
        code_file = str(self.ws / "src" / "stuck.py")

        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": code_file}},
        })

        # Attempt 1 -> continue
        _, stop1 = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(stop1.get("decision"), "continue")

        # Attempt 2 -> continue
        _, stop2 = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(stop2.get("decision"), "continue")

        # Attempt 3 -> trips anti-deadlock valve -> allow
        _, stop3 = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(stop3.get("decision"), "allow")


if __name__ == "__main__":
    unittest.main()
