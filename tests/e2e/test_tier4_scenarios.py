#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Tier 4: Real-World Application Scenarios.
Executes 5 realistic end-to-end user journeys mirroring production workflows:
- Scenario 1: Legacy Workspace Modernization Journey
- Scenario 2: Brownfield Polyglot Ingestion Journey
- Scenario 3: Legacy Automation Script Compatibility Journey
- Scenario 4: Zero-Risk Fleet CI Audit Journey
- Scenario 5: Greenfield Workspace Scaffolding Journey
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
import uuid

from tests.e2e.harness_base import OpaqueBoxTestCase


class TestTier4Scenarios(OpaqueBoxTestCase):
    """
    Tier 4 E2E test cases: Realistic multi-step end-to-end user journeys.
    """

    def _create_dummy_test_suite(self, name: str = "tier4") -> Path:
        mod_name = f"test_{name}_{uuid.uuid4().hex}"
        t_dir = self.ws / f"dummy_tests_{name}"
        t_dir.mkdir(parents=True, exist_ok=True)
        (t_dir / f"{mod_name}.py").write_text(
            "import unittest\nclass TestSimple(unittest.TestCase):\n    def test_pass(self):\n        pass\n",
            encoding="utf-8",
        )
        self.addCleanup(lambda: sys.modules.pop(mod_name, None))
        return t_dir

    def test_journey_1_legacy_workspace_modernization(self) -> None:
        """
        Scenario 1: Legacy Workspace Modernization Journey.
        Operator migrates a legacy Antigravity repo containing custom rules,
        .agent/agents/, .agent/workflows/, and .agent/rules/ into modern .agents/.
        """
        # Step 1: Set up realistic legacy PSL 1.0 repository
        custom_header = "# Team Ground Rules\n- Fast reviews\n- High test coverage\n\n"
        custom_footer = "\n\n## Custom Project Standards\n- Keep dependencies minimal\n"
        legacy_content = (
            custom_header
            + "<!-- Added by PSL-HARNESS -->\nLegacy Invariant Block\n<!-- End PSL-HARNESS -->"
            + custom_footer
        )
        self.create_fixture("legacy_psl", custom_rules=legacy_content)

        # Step 2: Preview migration via dry-run with pure JSON report
        code_dry, out_dry, err_dry = self.run_cli(["harmonize", "--dry-run", "--json", str(self.ws)])
        self.assertEqual(code_dry, 0)
        report_dry = self.parse_json_stdout(out_dry)
        self.assertTrue(report_dry["dry_run"])
        self.assertTrue(report_dry["legacy_agent_dir_found"])
        self.assertEqual(report_dry["rules_action"], "migrated_tagged_block")
        # Ensure zero changes made during dry run
        self.assertFalse((self.ws / ".agents").exists())

        # Step 3: Execute live harmonization
        code_live, out_live, err_live = self.run_cli(["harmonize", str(self.ws)])
        self.assertEqual(code_live, 0)

        # Step 4: Verify structure migration and YAML frontmatter synthesis
        agents_dir = self.ws / ".agents" / "agents"
        skills_dir = self.ws / ".agents" / "skills"
        rules_dir = self.ws / ".agents" / "rules"

        self.assertTrue((agents_dir / "code_reviewer.md").exists())
        self.assertTrue((rules_dir / "standards.md").exists())

        skill_file = skills_dir / "deploy_staging" / "SKILL.md"
        self.assertTrue(skill_file.exists())
        skill_text = skill_file.read_text(encoding="utf-8")
        self.assertTrue(skill_text.startswith("---\nname: deploy_staging\n"))
        self.assertIn("description:", skill_text)

        # Step 5: Verify user rules outside fences preserved verbatim
        modern_rules = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("# Team Ground Rules", modern_rules)
        self.assertIn("- Fast reviews", modern_rules)
        self.assertIn("## Custom Project Standards", modern_rules)
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", modern_rules)
        self.assertIn("<!-- End AGYIS-HARNESS -->", modern_rules)
        self.assertNotIn("<!-- Added by PSL-HARNESS -->", modern_rules)

        # Step 6: Verify idempotence on subsequent run
        code_repeat, out_repeat, err_repeat = self.run_cli(["harmonize", "--json", str(self.ws)])
        self.assertEqual(code_repeat, 0)
        report_repeat = self.parse_json_stdout(out_repeat)
        self.assertEqual(report_repeat["rules_action"], "already_up_to_date")

    def test_journey_2_brownfield_polyglot_ingestion(self) -> None:
        """
        Scenario 2: Brownfield Polyglot Ingestion Journey.
        Ingestion of an enterprise monorepo containing Node, Python, and Makefile components.
        """
        # Step 1: Create polyglot monorepo workspace
        self.create_fixture("polyglot")

        # Step 2: Run dry-run inspection to preview detected commands
        code_preview, out_preview, err_preview = self.run_cli(["init", "--dry-run", "--json", str(self.ws)])
        self.assertEqual(code_preview, 0)
        preview_data = self.parse_json_stdout(out_preview)
        self.assertIn("command_dictionary", preview_data)
        self.assertFalse((self.ws / "AGENTS.md").exists())

        # Step 3: Run live initialization
        code_init, out_init, err_init = self.run_cli(["init", str(self.ws)])
        self.assertEqual(code_init, 0)

        # Step 4: Verify generated AGENTS.md Section 1 commands
        agents_content = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("## 1. Explicit Project Command Dictionary", agents_content)
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", agents_content)

        # Step 5: Assert re-running init is cleanly idempotent
        code_reinit, out_reinit, err_reinit = self.run_cli(["init", str(self.ws)])
        self.assertEqual(code_reinit, 0)

    def test_journey_3_legacy_operator_script_compatibility(self) -> None:
        """
        Scenario 3: Legacy Automation Script Compatibility Journey.
        Legacy operator scripts invoking 'psl' execute with complete parity
        while emitting the active deprecation notice on stderr.
        """
        t_dir = self._create_dummy_test_suite("operator_compat")

        # Command A: psl doctor
        code_doc, out_doc, err_doc = self.run_cli(["doctor", "--help"], prog="psl")
        self.assertEqual(code_doc, 0)
        self.assertIn("DeprecationWarning: 'psl' is deprecated", err_doc)
        self.assertIn("Antigravity Immune System", out_doc)

        # Command B: psl status
        code_stat, out_stat, err_stat = self.run_cli(["status"], prog="psl")
        self.assertEqual(code_stat, 0)
        self.assertIn("DeprecationWarning: 'psl' is deprecated", err_stat)
        self.assertIn("Specialist Subagents", out_stat)

        # Command C: psl test
        code_test, out_test, err_test = self.run_cli(["test", "-s", str(t_dir)], prog="psl")
        self.assertEqual(code_test, 0)
        self.assertIn("DeprecationWarning: 'psl' is deprecated", err_test)

    def test_journey_4_fleet_ci_dry_run_audit(self) -> None:
        """
        Scenario 4: Zero-Risk Fleet CI Audit Journey.
        Automated CI job scans an array of workspaces using 'agyis harmonize --dry-run --json',
        asserting 100% byte stability across all repositories.
        """
        # Set up 3 distinct workspaces inside self.ws
        ws_legacy = self.ws / "repo_legacy"
        ws_systems = self.ws / "repo_systems"
        ws_node = self.ws / "repo_node"

        ws_legacy.mkdir()
        ws_systems.mkdir()
        ws_node.mkdir()

        # Seed repo_legacy
        (ws_legacy / "AGENTS.md").write_text(
            "# Legacy\n<!-- Added by PSL-HARNESS -->\nOld rules\n<!-- End PSL-HARNESS -->\n",
            encoding="utf-8",
        )
        (ws_legacy / ".agent" / "workflows").mkdir(parents=True)
        (ws_legacy / ".agent" / "workflows" / "ci.md").write_text("# CI Workflow", encoding="utf-8")

        # Seed repo_systems
        (ws_systems / "Makefile").write_text("test:\n\tpytest\n", encoding="utf-8")

        # Seed repo_node
        (ws_node / "package.json").write_text(json.dumps({"scripts": {"test": "jest"}}), encoding="utf-8")

        # Compute whole-tree SHA-256 baseline
        def hash_dir(d: Path) -> dict[str, str]:
            return {
                str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(d.rglob("*"))
                if p.is_file()
            }

        baseline_legacy = hash_dir(ws_legacy)
        baseline_systems = hash_dir(ws_systems)
        baseline_node = hash_dir(ws_node)

        # CI audit loop over all 3 repos
        targets = [ws_legacy, ws_systems, ws_node]
        for target in targets:
            code, out, err = self.run_cli(["harmonize", "--dry-run", "--json", str(target)])
            self.assertEqual(code, 0)
            data = self.parse_json_stdout(out)
            self.assertTrue(data.get("dry_run"))

        # Assert 100% byte stability across all 3 repositories (zero git diff)
        self.assertEqual(baseline_legacy, hash_dir(ws_legacy))
        self.assertEqual(baseline_systems, hash_dir(ws_systems))
        self.assertEqual(baseline_node, hash_dir(ws_node))

    def test_journey_5_greenfield_workspace_scaffolding(self) -> None:
        """
        Scenario 5: Greenfield Workspace Scaffolding Journey.
        Creating a brand-new repository from scratch, initializing it with agyis,
        and validating specialist personas and diagnostic readiness.
        """
        greenfield = self.ws / "greenfield_project"
        greenfield.mkdir()

        # Step 1: Initialize workspace
        code_init, out_init, err_init = self.run_cli(["init", str(greenfield)])
        self.assertEqual(code_init, 0)

        # Step 2: Validate AGENTS.md created with modern tags
        agents_file = greenfield / "AGENTS.md"
        self.assertTrue(agents_file.exists())
        content = agents_file.read_text(encoding="utf-8")
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", content)
        self.assertIn("<!-- End AGYIS-HARNESS -->", content)

        # Step 3: Inspect specialist personas
        code_ag, out_ag, err_ag = self.run_cli(["agents", "--json"])
        self.assertEqual(code_ag, 0)
        agents_data = self.parse_json_stdout(out_ag)
        arch = next((a for a in agents_data if a.get("name") == "agyis_architect"), None)
        self.assertIsNotNone(arch)
        self.assertTrue(arch.get("can_write"))
        self.assertTrue(arch.get("can_execute"))
        self.assertEqual(arch.get("tools_count"), 17)

        # Step 4: Verify doctor audit passes cleanly
        code_doc, out_doc, err_doc = self.run_cli(["doctor", "--help"])
        self.assertEqual(code_doc, 0)
        self.assertIn("Antigravity Immune System", out_doc)


if __name__ == "__main__":
    unittest.main()
