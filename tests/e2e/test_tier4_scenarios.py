#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Tier 4: Real-World Scenarios & User Journeys (Issues #41, #42, #43, #46, and REA Cleanroom Harmonization).
Executes end-to-end user journeys mirroring production workflows:
- Scenario 1: Multi-Agent Swarm Coordination Journey
- Scenario 2: Diagnostic Scratch Investigation Journey
- Scenario 5: Bug Report Submission with Doctor Integration Journey
- Scenario 6: REA Cleanroom Specification Authoring & Manifest Clearance Journey
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import unittest
import uuid

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

    def test_s5_bug_report_submission_with_doctor_integration_journey(self) -> None:
        """Simulates automated bug reporting workflow harvesting doctor telemetry into issue templates."""
        # Step 1: Harvest doctor diagnostics
        code, out, _ = self.run_cli(["doctor", "--json"])
        self.assertEqual(code, 0)
        audit = json.loads(out)
        python_info = f"Python: CPython {audit.get('hermetic_python_available', 'standard')}"

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

    def test_journey_6_rea_cleanroom_specification_and_manifest_clearance(self) -> None:
        """
        Scenario 6: REA Cleanroom Specification Authoring, Manifest Clearance & Fence Gating.
        Simulates an agent executing cleanroom binary reconstruction:
        1. Initialize workspace with --experimental-rea opt-in.
        2. Author declarative cleanroom specification in docs/specs/crypto_core.md.
        3. Attempting to stop without verification is gated with cleanroom-specific prompt (no unit test coercion).
        4. Formal manifest clearance in .agents/ledger/manifest.json unblocks completion fence.
        5. Code-in-specs guard: authoring executable code in docs/specs/ triggers dual dirty state.
        6. Cleanroom or project verification clears fence and allows exit.
        """
        conv_id = f"journey6_conv_{uuid.uuid4().hex[:8]}"

        # Step 1: Initialize cleanroom workspace
        code_init, out_init, err_init = self.run_cli(["init", "--experimental-rea", str(self.ws)])
        self.assertEqual(code_init, 0)
        self.assertTrue((self.ws / ".agents" / "ledger").is_dir())

        # Step 2: Author declarative cleanroom specification
        spec_dir = self.ws / "docs" / "specs"
        spec_dir.mkdir(parents=True, exist_ok=True)
        spec_file = spec_dir / "crypto_core.md"
        spec_file.write_text("# Cleanroom Specification: Crypto Core\n\n## Obligations\n- OBL-01: ChaCha20-Poly1305\n", encoding="utf-8")

        # Record file edit through completion-fence hook
        edit_payload = json.dumps({
            "action": "record_edit",
            "file_path": str(spec_file),
            "conversation_id": conv_id,
            "cwd": str(self.ws),
        })
        code_e, out_e, err_e = self.run_cli(["hook", "completion-fence"], stdin_input=edit_payload)
        self.assertEqual(code_e, 0)

        # Step 3: Stop evaluation without cleanroom verification
        stop_payload = json.dumps({
            "event": "Stop",
            "conversation_id": conv_id,
            "cwd": str(self.ws),
        })
        code_s1, out_s1, err_s1 = self.run_cli(["hook", "completion-fence"], stdin_input=stop_payload)
        self.assertEqual(code_s1, 0)
        data_s1 = self.parse_json_stdout(out_s1)

        # Decision MUST be 'continue' (blocking stop) with cleanroom-specific directive
        self.assertEqual(data_s1.get("decision"), "continue")
        reason_s1 = data_s1.get("reason", "")
        self.assertIn("Cleanroom Verification Required", reason_s1)
        self.assertIn("crypto_core.md", reason_s1)
        self.assertIn("rea verify-reconstruction", reason_s1)
        # CRUCIAL INVARIANT: Must NOT demand unit tests ('agyis test') for declarative specs
        self.assertNotIn("agyis test", reason_s1)

        # Step 4: Author formal cleanroom clearance manifest
        manifest_file = self.ws / ".agents" / "ledger" / "manifest.json"
        manifest_payload = {
            "status": "verified",
            "evidence_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "obligations": [
                {"id": "OBL-01", "status": "satisfied", "description": "ChaCha20 implementation verified"}
            ],
        }
        manifest_file.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

        # Step 5: Stop evaluation with verified manifest -> completion fence unblocked!
        code_s2, out_s2, err_s2 = self.run_cli(["hook", "completion-fence"], stdin_input=stop_payload)
        self.assertEqual(code_s2, 0)
        data_s2 = self.parse_json_stdout(out_s2)
        self.assertEqual(data_s2.get("decision"), "allow")

        # Step 6: Code-in-specs guard (DEF-01): authoring executable code inside docs/specs/
        code_in_spec = spec_dir / "exploit.py"
        code_in_spec.write_text("def exploit(): return 1\n", encoding="utf-8")
        code_edit_payload = json.dumps({
            "action": "record_edit",
            "file_path": str(code_in_spec),
            "conversation_id": conv_id,
            "cwd": str(self.ws),
        })
        code_ce, out_ce, err_ce = self.run_cli(["hook", "completion-fence"], stdin_input=code_edit_payload)
        self.assertEqual(code_ce, 0)

        # Stop evaluation -> code_dirty is True, must demand test suite execution!
        code_s3, out_s3, err_s3 = self.run_cli(["hook", "completion-fence"], stdin_input=stop_payload)
        self.assertEqual(code_s3, 0)
        data_s3 = self.parse_json_stdout(out_s3)
        self.assertEqual(data_s3.get("decision"), "continue")
        reason_s3 = data_s3.get("reason", "")
        self.assertIn("Verification Required", reason_s3)
        self.assertIn("exploit.py", reason_s3)

        # Step 7: Clear verification via verifier command check
        verify_cmd_payload = json.dumps({
            "action": "check_command_verification",
            "command": "rea verify-reconstruction",
            "exit_code": 0,
            "conversation_id": conv_id,
            "cwd": str(self.ws),
        })
        code_vc, out_vc, err_vc = self.run_cli(["hook", "completion-fence"], stdin_input=verify_cmd_payload)
        self.assertEqual(code_vc, 0)

        # Stop evaluation -> both spec_dirty and code_dirty cleared, stop allowed!
        code_s4, out_s4, err_s4 = self.run_cli(["hook", "completion-fence"], stdin_input=stop_payload)
        self.assertEqual(code_s4, 0)
        data_s4 = self.parse_json_stdout(out_s4)
        self.assertEqual(data_s4.get("decision"), "allow")


if __name__ == "__main__":
    unittest.main()
