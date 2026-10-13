#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Tier 3: Cross-Feature Interactions & Pairwise Combinations.
Validates integrations between distinct product subsystems:
- PSL shim deprecation isolation + JSON stdout purity
- Init then Harmonize lifecycle idempotence
- Harmonize migration then Doctor health audit
- Polyglot manifest precedence + Section 1 command extraction
- XDG config precedence + workspace initialization
- Lifecycle hook dual-runner alternating recognition
- Doctor auto-healing + workspace file safety
- Skills synchronization + agent discovery coexistence
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import unittest
import uuid

from tests.e2e.harness_base import OpaqueBoxTestCase


class TestTier3Combinations(OpaqueBoxTestCase):
    """
    Tier 3 E2E test cases: Pairwise cross-feature interactions and integration contracts.
    """

    def _create_dummy_test_suite(self, name: str = "tier3") -> Path:
        mod_name = f"test_{name}_{uuid.uuid4().hex}"
        t_dir = self.ws / f"dummy_tests_{name}"
        t_dir.mkdir(parents=True, exist_ok=True)
        (t_dir / f"{mod_name}.py").write_text(
            "import unittest\nclass TestSimple(unittest.TestCase):\n    def test_pass(self):\n        pass\n",
            encoding="utf-8",
        )
        self.addCleanup(lambda: sys.modules.pop(mod_name, None))
        return t_dir

    def test_cross_psl_harmonize_json_stderr_isolation(self) -> None:
        """Assures 'psl harmonize --json' isolates deprecation notice to stderr and keeps stdout pure JSON."""
        self.create_fixture("legacy_psl")
        code, out, err = self.run_cli(
            ["harmonize", "--dry-run", "--json", str(self.ws)], prog="psl"
        )
        self.assertEqual(code, 0)
        # Stderr must contain the deprecation notice
        self.assertIn("DeprecationWarning: 'psl' is deprecated", err)
        # Stdout must be strictly valid JSON without deprecation contamination
        data = self.parse_json_stdout(out)
        self.assertTrue(data.get("dry_run"))
        self.assertTrue(data.get("legacy_agent_dir_found"))

    def test_cross_init_then_harmonize_idempotence(self) -> None:
        """Assures running 'agyis init' followed by 'agyis harmonize' preserves workspace stability."""
        # Step 1: Initialize workspace
        code_i, out_i, err_i = self.run_cli(["init", str(self.ws)])
        self.assertEqual(code_i, 0)
        content_after_init = (self.ws / "AGENTS.md").read_text(encoding="utf-8")

        # Step 2: Harmonize the initialized workspace
        code_h, out_h, err_h = self.run_cli(["harmonize", str(self.ws)])
        self.assertEqual(code_h, 0)
        content_after_harm = (self.ws / "AGENTS.md").read_text(encoding="utf-8")

        # Rules action should report already up to date
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", content_after_harm)
        self.assertNotIn("<!-- Added by PSL-HARNESS -->", content_after_harm)
        self.assertEqual(content_after_init, content_after_harm)

    def test_cross_harmonize_then_doctor_health(self) -> None:
        """Assures migrating a legacy workspace via 'harmonize' leaves environment in clean health."""
        self.create_fixture("legacy_psl")
        code_h, out_h, err_h = self.run_cli(["harmonize", str(self.ws)])
        self.assertEqual(code_h, 0)

        code_d, out_d, err_d = self.run_cli(["doctor", "--json"])
        self.assertEqual(code_d, 0)
        data = self.parse_json_stdout(out_d)
        self.assertGreaterEqual(data["summary"]["ok"], 1)

    def test_cross_polyglot_precedence_and_command_dictionary(self) -> None:
        """Assures multi-manifest polyglot repository formats unified command dictionary."""
        self.create_fixture("polyglot")
        code, out, err = self.run_cli(["init", str(self.ws)])
        self.assertEqual(code, 0)

        content = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("## 1. Explicit Project Command Dictionary", content)
        # Should format detected npm scripts and make target commands
        self.assertTrue("pnpm test" in content or "make" in content)

    def test_cross_xdg_path_precedence_and_init(self) -> None:
        """Assures workspace init executes correctly under explicit AGYIS_CONFIG_DIR precedence."""
        dir_agyis = self.ws / "xdg_agyis"
        dir_psl = self.ws / "xdg_psl"
        dir_agyis.mkdir(parents=True, exist_ok=True)
        dir_psl.mkdir(parents=True, exist_ok=True)

        env = {
            "AGYIS_CONFIG_DIR": str(dir_agyis),
            "PSL_CONFIG_DIR": str(dir_psl),
        }
        code, out, err = self.run_cli(["init", "--dry-run", "--json", str(self.ws)], env_overrides=env)
        self.assertEqual(code, 0)
        data = self.parse_json_stdout(out)
        self.assertTrue(data.get("success"))

    def test_cross_lifecycle_hooks_dual_runner_alternating(self) -> None:
        """Assures command safety hook permits alternating invocations of agyis and psl runners."""
        runners = [
            "agyis test",
            "psl test",
            "./agyis test",
            "./psl test",
            "python3 -m harness.cli test",
        ]
        for cmd in runners:
            payload = json.dumps({"tool_name": "run_command", "tool_args": {"CommandLine": cmd}})
            code, out, err = self.run_cli(["hook", "command-safety"], stdin_input=payload)
            self.assertEqual(code, 0)
            data = self.parse_json_stdout(out)
            self.assertEqual(data.get("decision"), "allow", f"Failed for runner command: {cmd}")

    def test_cross_doctor_heal_preserves_workspace_configs(self) -> None:
        """Assures 'doctor --heal' does not overwrite or corrupt existing workspace rules."""
        custom_content = "# Pre-existing Workspace Rules\n- Custom invariant\n"
        (self.ws / "AGENTS.md").write_text(custom_content, encoding="utf-8")

        code, out, err = self.run_cli(["doctor", "--heal", "--json"])
        self.assertEqual(code, 0)

        # Workspace AGENTS.md must remain completely untouched
        self.assertEqual((self.ws / "AGENTS.md").read_text(encoding="utf-8"), custom_content)

    def test_cross_skills_sync_and_agent_discovery(self) -> None:
        """Assures syncing modular skills to workspace preserves specialist persona discovery."""
        code_s, out_s, err_s = self.run_cli(["skills", "--sync", "-w", str(self.ws)])
        self.assertEqual(code_s, 0)

        code_a, out_a, err_a = self.run_cli(["agents", "--json"])
        self.assertEqual(code_a, 0)
        data = self.parse_json_stdout(out_a)
        agent_names = [a.get("name") for a in data]
        self.assertIn("agyis_architect", agent_names)

    def test_cross_harmonize_then_test_completion_fence(self) -> None:
        """Assures harmonizing a workspace followed by test execution unblocks completion fence."""
        self.create_fixture("legacy_psl")
        code_h, out_h, err_h = self.run_cli(["harmonize", str(self.ws)])
        self.assertEqual(code_h, 0)

        # Execute tests via test runner
        t_dir = self._create_dummy_test_suite("fence_sync")
        code_t, out_t, err_t = self.run_cli(["test", "-s", str(t_dir)])
        self.assertEqual(code_t, 0)

        # Stop event hook should evaluate cleanly
        stop_payload = json.dumps({"event": "Stop", "conversation_id": "cross_test_conv"})
        code_f, out_f, err_f = self.run_cli(["hook", "completion-fence"], stdin_input=stop_payload)
        self.assertEqual(code_f, 0)
        data = self.parse_json_stdout(out_f)
        self.assertIn(data.get("decision"), ["allow", "continue"])


if __name__ == "__main__":
    unittest.main()
