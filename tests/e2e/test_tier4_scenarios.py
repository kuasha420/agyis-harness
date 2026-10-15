#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Tier 4: Real-World Scenarios & User Journeys (Issues #41 through #46).
Executes 5 end-to-end user journeys mirroring production workflows:
- Scenario 1: Multi-Agent Swarm Coordination Journey
- Scenario 2: Diagnostic Scratch Investigation Journey
- Scenario 3: Cleanroom Hardware Specification Authoring Journey
- Scenario 4: Workstation Diagnostics & REA Health Triage Journey
- Scenario 5: Bug Report Submission with Doctor Integration Journey
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import unittest

from harness.delivery.constants import REPO_ROOT
from harness.runtime.doctor import run_doctor
from tests.e2e.harness_base import OpaqueBoxTestCase


class TestTier4Scenarios(OpaqueBoxTestCase):
    """
    Tier 4 E2E tests validating complete real-world multi-step user journeys.
    """

    def test_s1_multi_agent_swarm_coordination_journey(self) -> None:
        """Simulates full multi-agent swarm coordination across teamwork and ledger paths."""
        self.create_fixture("coordination")
        conv_id = "journey_swarm_1"

        dispatch_path = str(self.ws / ".agents" / "teamwork" / "DISPATCH.md")
        progress_path = str(self.ws / ".agents" / "teamwork" / "progress.md")
        obligations_path = str(self.ws / ".agents" / "ledger" / "obligations.json")

        # Step 1: Coordinator sets up dispatch
        # (Coordination files exempt from dirty state in verification fence)
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": dispatch_path, "CodeContent": "# Dispatch"}},
        })

        # Step 2: Worker 1 inspects dispatch repeatedly
        for _ in range(5):
            code, resp = self.run_hook("anti-loop", {
                "conversationId": conv_id,
                "toolCall": {"name": "view_file", "args": {"AbsolutePath": dispatch_path}},
            })
            self.assertEqual(code, 0)
            self.assertEqual(resp.get("decision"), "allow")

        # Step 3: Worker 1 reads progress heartbeats
        for _ in range(8):
            code, resp = self.run_hook("anti-loop", {
                "conversationId": conv_id,
                "toolCall": {"name": "view_file", "args": {"Path": progress_path}},
            })
            self.assertEqual(code, 0)
            self.assertEqual(resp.get("decision"), "allow")

        # Step 4: Worker 2 views obligations ledger
        for _ in range(6):
            code, resp = self.run_hook("anti-loop", {
                "conversationId": conv_id,
                "toolCall": {"name": "view_file", "args": {"TargetFile": obligations_path}},
            })
            self.assertEqual(code, 0)
            self.assertEqual(resp.get("decision"), "allow")

        # Step 5: Workers finish coordination turn and terminate cleanly
        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "allow")

    def test_s2_diagnostic_scratch_investigation_journey(self) -> None:
        """Simulates an investigation where agent authors scratch scripts without dirtying repo."""
        conv_id = "journey_scratch_diag"
        brain_scratch = "/home/kuasha/.gemini/antigravity/brain/session_diag/scratch/repro.py"
        tmp_scratch = "/tmp/probe_output.py"

        # Step 1: Agent creates a scratch reproduction script
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": brain_scratch, "CodeContent": "print('testing edge case')"},
            },
        })

        # Step 2: Agent creates second probe in system temp directory
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": tmp_scratch, "CodeContent": "import sys; print(sys.version)"},
            },
        })

        # Step 3: Agent concludes diagnosis and terminates immediately without running repo tests
        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(
            stop_resp.get("decision"),
            "allow",
            "Diagnostic task with only scratch files was falsely blocked from terminating",
        )

    def test_s3_cleanroom_hardware_specification_authoring_journey(self) -> None:
        """Simulates cleanroom spec authoring, verification gating, and clearance upon passing tests."""
        conv_id = "journey_cleanroom_spec"
        spec_path = str(self.ws / "docs" / "specs" / "display_controller.md")

        # Step 1: Reverse engineer authors cleanroom specification
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {
                "name": "write_to_file",
                "args": {
                    "TargetFile": spec_path,
                    "CodeContent": "# Display Controller Specification\n\nRegister 0x40: VSYNC\n",
                },
            },
        })

        # Step 2: Agent attempts to stop prematurely -> blocked by completion fence
        _, stop1 = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(stop1.get("decision"), "continue")
        self.assertIn("cleanroom contract", stop1.get("reason", "").lower())

        # Step 3: Agent executes verification test command -> exit code 0
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "exitCode": 0,
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "./agyis test", "Cwd": str(self.ws)},
            },
        })

        # Step 4: Agent retries stop -> allowed cleanly
        code, stop2 = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop2.get("decision"), "allow")

    def test_s4_workstation_diagnostics_and_rea_health_triage_journey(self) -> None:
        """Simulates workstation environment health check integrating REA tooling diagnostics."""
        # Execute doctor audit
        code, stdout, stderr = self.run_cli(["doctor"])
        self.assertEqual(code, 0)
        self.assertIn("AGYIS WORKSTATION DOCTOR", stdout)

        # Execute programmatic doctor audit and inspect REA diagnostics
        code, out, _ = self.run_cli(["doctor", "--json"])
        self.assertEqual(code, 0)
        audit = json.loads(out)
        self.assertIn("rea_tooling", audit)
        rea_data = audit["rea_tooling"]
        self.assertIn("status", rea_data)
        self.assertIn("providers", rea_data)
        self.assertIn("mcp_configured", rea_data)

        # Assert non-fatal grading
        self.assertEqual(audit["summary"]["missing"], 0)

    def test_s5_bug_report_submission_with_doctor_integration_journey(self) -> None:
        """Simulates automated bug reporting workflow harvesting doctor telemetry into issue templates."""
        # Step 1: Harvest doctor diagnostics
        code, out, _ = self.run_cli(["doctor", "--json"])
        self.assertEqual(code, 0)
        audit = json.loads(out)
        python_info = f"Python: CPython {audit.get('hermetic_python_available', 'standard')}"
        rea_status = audit.get("rea_tooling", {}).get("status", "unknown")

        # Step 2: Query active harness version
        code, version_out, _ = self.run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertTrue(len(version_out.strip()) > 0)

        # Step 3: Verify issue template availability (skip if pending Milestone M4)
        template_path = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml"
        if not template_path.exists():
            self.skipTest("Pending implementation in Milestone M4: bug_report.yml not yet created")

        tmpl_content = template_path.read_text(encoding="utf-8")

        # Step 4: Validate template accepts harvested data
        self.assertIn("harness_version", tmpl_content)
        self.assertIn("host_toolchain_versions", tmpl_content)
        self.assertIn("problem_description", tmpl_content)


if __name__ == "__main__":
    unittest.main()
