#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Tier 3: Cross-Feature Interactions (Issues #41, #42, #43, and #46).
Validates critical cross-feature interactions and subsystem combinations:
- Interaction 1: Anti-Loop Test Reset + Stop-Fence Clearance
- Interaction 2: Doctor Toolchain Audit + Issue Template Correlation
- Interaction 3: Multi-Agent Teamwork Views + Scratch Script Authoring
- Interaction 4: Diverse Universal Test Runner Patterns Recognition
- Interaction 5: Anti-Deadlock Safety Valve Trips on Attempt Three
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import unittest
from unittest.mock import MagicMock, patch
import uuid

from harness.delivery.constants import REPO_ROOT
from harness.runtime.doctor import run_doctor
from tests.e2e.harness_base import OpaqueBoxTestCase


class TestTier3Combinations(OpaqueBoxTestCase):
    """
    Tier 3 E2E tests validating cross-feature and multi-subsystem interactions.
    """

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

    def test_c5_doctor_toolchain_audit_plus_template_correlation(self) -> None:
        """Assures doctor audit metrics correspond to host_toolchain_versions in issue template."""
        code, out, _ = self.run_cli(["doctor", "--json"])
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertIn("os_family", report)
        self.assertIn("summary", report)

        template_path = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml"
        if template_path.exists():
            tmpl_content = template_path.read_text(encoding="utf-8")
            self.assertIn("host_toolchain_versions", tmpl_content)

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

    def test_cross_skills_sync_includes_reverse_engineer_anything(self) -> None:
        """Assures modular skills synchronize cleanly and REA skill provisions on-demand (ADR-014/ADR-032)."""
        from harness.runtime.healing import provision_rea_skill

        # Execute workspace skill synchronization
        code_s, out_s, err_s = self.run_cli(["skills", "--sync", "-w", str(self.ws)])
        self.assertEqual(code_s, 0)

        # Verify other modular skills coexist seamlessly
        self.assertTrue((self.ws / ".agents" / "skills" / "storage-ops" / "SKILL.md").is_file())
        self.assertTrue((self.ws / ".agents" / "skills" / "audio-ops" / "SKILL.md").is_file())

        # Inspect public listing contract for base skills
        code_l, out_l, err_l = self.run_cli(["skills", "--json"])
        self.assertEqual(code_l, 0)
        skills_data = self.parse_json_stdout(out_l)
        self.assertTrue(any(s.get("name") == "storage-ops" for s in skills_data))

        # ADR-014: reverse-engineer-anything must NOT be vendored into harness/skills
        harness_rea = REPO_ROOT / "harness" / "skills" / "reverse-engineer-anything"
        self.assertFalse(harness_rea.exists(), "reverse-engineer-anything must not be vendored in harness/skills")

        # Create mock upstream package and test on-demand dynamic provisioning
        mock_pkg_root = self.ws / "mock_rea_package"
        mock_rea_src = mock_pkg_root / "skills" / "reverse-engineer-anything"
        mock_rea_src.mkdir(parents=True)
        (mock_rea_src / "SKILL.md").write_text(
            "---\nname: reverse-engineer-anything\ndescription: Dynamic REA skill\nmetadata:\n  version: '42'\n---\n# REA Guide",
            encoding="utf-8",
        )
        (mock_rea_src / "references").mkdir()
        (mock_rea_src / "references" / "native-and-artifacts.md").write_text("# Native", encoding="utf-8")

        mock_prov_json = json.dumps({
            "server_identity": {
                "package": {
                    "name": "rea-agents",
                    "root_path": str(mock_pkg_root),
                }
            }
        })
        mock_proc = MagicMock(returncode=0, stdout=mock_prov_json, stderr="")

        target_skills = self.ws / ".agents" / "skills"
        with patch("subprocess.run", return_value=mock_proc):
            prov_path = provision_rea_skill(target_skills, link=False, allow_download=False)
            self.assertIsNotNone(prov_path)
            self.assertTrue((prov_path / "SKILL.md").is_file())
            content = (prov_path / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("name: reverse-engineer-anything", content)
            self.assertTrue((prov_path / "references" / "native-and-artifacts.md").is_file())


if __name__ == "__main__":
    unittest.main()
