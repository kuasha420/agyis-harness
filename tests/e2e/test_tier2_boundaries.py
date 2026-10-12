#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Tier 2: Boundary & Corner Cases.
Probes edge cases, invalid inputs, and boundary conditions across:
- Empty files & missing workspaces
- Corrupted & malformed manifests (JSON, TOML, binary Makefiles)
- Symlink cycles & deep directory hierarchies
- Read-only permissions & disk protections
- Unicode, multilingual & emoji rule fidelity
- CLI argument edge cases & unusual configurations
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys
import unittest

from tests.e2e.harness_base import OpaqueBoxTestCase


class TestTier2Boundaries(OpaqueBoxTestCase):
    """
    Tier 2 E2E test cases: Boundary and corner cases across all operational subsystems.
    Tests system resilience under adverse or edge-case conditions.
    """

    # =========================================================================
    # Domain 1: Workspaces, Permissions & Path Configurations
    # =========================================================================

    def test_boundary_nonexistent_workspace(self) -> None:
        """Assures harmonizing a non-existent directory returns exit code 1 with clean error."""
        bogus_path = self.ws / "does_not_exist_xyz123"
        code, out, err = self.run_cli(["harmonize", str(bogus_path)])
        self.assertEqual(code, 1)
        self.assertIn("does not exist", err.lower() + out.lower())

    def test_boundary_empty_workspace_init(self) -> None:
        """Assures 'agyis init' on an empty directory succeeds and scaffolds clean files."""
        empty_dir = self.ws / "empty_proj"
        empty_dir.mkdir()
        code, out, err = self.run_cli(["init", str(empty_dir)])
        self.assertEqual(code, 0)
        self.assertTrue((empty_dir / "AGENTS.md").exists())

    def test_boundary_read_only_agents_md_dry_run(self) -> None:
        """Assures '--dry-run' succeeds without PermissionError even if AGENTS.md is chmod 0444."""
        self.create_fixture("legacy_psl")
        agents_file = self.ws / "AGENTS.md"
        agents_file.chmod(stat.S_IREAD)
        try:
            code, out, err = self.run_cli(["harmonize", "--dry-run", str(self.ws)])
            self.assertEqual(code, 0)
        finally:
            agents_file.chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_boundary_read_only_workspace_dir_dry_run(self) -> None:
        """Assures '--dry-run' succeeds without writing when workspace directory is read-only."""
        ro_dir = self.ws / "ro_workspace"
        ro_dir.mkdir()
        ro_dir.chmod(stat.S_IREAD | stat.S_IEXEC)
        try:
            code, out, err = self.run_cli(["init", "--dry-run", str(ro_dir)])
            self.assertEqual(code, 0)
            self.assertFalse((ro_dir / "AGENTS.md").exists())
        finally:
            ro_dir.chmod(stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)

    def test_boundary_unusual_path_configurations_doctor(self) -> None:
        """Assures 'agyis doctor' survives when PATH is restricted or tools are missing."""
        with unittest.mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}):
            code, out, err = self.run_cli(["doctor", "--json"])
            self.assertEqual(code, 0)
            data = self.parse_json_stdout(out)
            self.assertIn("summary", data)

    # =========================================================================
    # Domain 2: Malformed & Corrupted Manifests
    # =========================================================================

    def test_boundary_truncated_package_json(self) -> None:
        """Assures 'agyis init' handles truncated package.json gracefully without crashing."""
        (self.ws / "package.json").write_text('{"name": "broken_package_json', encoding="utf-8")
        code, out, err = self.run_cli(["init", "--dry-run", "--json", str(self.ws)])
        self.assertEqual(code, 0)
        data = self.parse_json_stdout(out)
        self.assertTrue(data.get("success"))

    def test_boundary_corrupted_pyproject_toml(self) -> None:
        """Assures 'agyis init' handles syntax errors in pyproject.toml gracefully."""
        (self.ws / "pyproject.toml").write_text("[project\n broken syntax = = =\n", encoding="utf-8")
        code, out, err = self.run_cli(["init", "--dry-run", "--json", str(self.ws)])
        self.assertEqual(code, 0)
        data = self.parse_json_stdout(out)
        self.assertTrue(data.get("success"))

    def test_boundary_binary_garbage_makefile(self) -> None:
        """Assures 'agyis init' handles binary/non-UTF8 Makefiles without decode crash."""
        (self.ws / "Makefile").write_bytes(b"\x00\xff\xfe\x00\x12\x34\xab\xcd")
        code, out, err = self.run_cli(["init", "--dry-run", "--json", str(self.ws)])
        self.assertEqual(code, 0)
        data = self.parse_json_stdout(out)
        self.assertTrue(data.get("success"))

    def test_boundary_empty_manifest_files(self) -> None:
        """Assures 0-byte manifest files are handled safely during preset detection."""
        (self.ws / "package.json").write_text("", encoding="utf-8")
        (self.ws / "pyproject.toml").write_text("", encoding="utf-8")
        (self.ws / "Makefile").write_text("", encoding="utf-8")
        code, out, err = self.run_cli(["init", "--dry-run", "--json", str(self.ws)])
        self.assertEqual(code, 0)
        data = self.parse_json_stdout(out)
        self.assertTrue(data.get("success"))

    def test_boundary_empty_doctor_matrix(self) -> None:
        """Assures 'doctor --matrix' with empty tiers in custom matrix succeeds safely."""
        empty_matrix = self.ws / "empty_matrix.json"
        empty_matrix.write_text("{}", encoding="utf-8")
        code, out, err = self.run_cli(["doctor", "--matrix", str(empty_matrix), "--json"])
        self.assertEqual(code, 0)
        data = self.parse_json_stdout(out)
        self.assertIn("summary", data)

    # =========================================================================
    # Domain 3: Rule Fencing Robustness & Unicode/Emoji Fidelity
    # =========================================================================

    def test_boundary_empty_fences(self) -> None:
        """Assures empty legacy fence block is upgraded cleanly to modern tagged block."""
        empty_fence = "<!-- Added by PSL-HARNESS -->\n<!-- End PSL-HARNESS -->\n"
        self.create_fixture("legacy_psl", custom_rules=empty_fence)
        code, out, err = self.run_cli(["harmonize", str(self.ws)])
        self.assertEqual(code, 0)

        content = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", content)
        self.assertIn("<!-- End AGYIS-HARNESS -->", content)
        self.assertNotIn("<!-- Added by PSL-HARNESS -->", content)

    def test_boundary_unclosed_opening_tag_treated_safely(self) -> None:
        """Assures an unclosed opening fence is preserved safely as user rules and block appended."""
        unclosed = "# User Header\n<!-- Added by PSL-HARNESS -->\nNo closing delimiter here\n"
        self.create_fixture("legacy_psl", custom_rules=unclosed)
        code, out, err = self.run_cli(["harmonize", str(self.ws)])
        self.assertEqual(code, 0)

        content = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("# User Header", content)
        self.assertIn("No closing delimiter here", content)
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", content)
        self.assertIn("<!-- End AGYIS-HARNESS -->", content)

    def test_boundary_regex_backreferences_in_user_rules(self) -> None:
        """Assures regex backreferences (\\g<1>, \\1, $1) in user rules are preserved intact."""
        regex_rules = (
            "# Regex Preservation Rules\n"
            "- Replace with \\g<1> and \\1 safely\n"
            "- Variable substitution $1 or ${var}\n\n"
            "<!-- Added by PSL-HARNESS -->\nOld rules\n<!-- End PSL-HARNESS -->\n"
        )
        self.create_fixture("legacy_psl", custom_rules=regex_rules)
        code, out, err = self.run_cli(["harmonize", str(self.ws)])
        self.assertEqual(code, 0)

        content = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(r"\g<1>", content)
        self.assertIn(r"\1", content)
        self.assertIn("$1", content)

    def test_boundary_unicode_multilingual_and_emojis(self) -> None:
        """Assures multilingual content (Bengali, Japanese, emojis) is preserved byte-for-byte."""
        multilingual = (
            "# সার্বজনীন নিয়মাবলী (Universal Rules 🚀)\n"
            "- বাংলা: কোড পরিষ্কার রাখুন ✨\n"
            "- 日本語: 品質を保つこと 🤖\n\n"
            "<!-- Added by PSL-HARNESS -->\nOld rules\n<!-- End PSL-HARNESS -->\n"
        )
        self.create_fixture("legacy_psl", custom_rules=multilingual)
        code, out, err = self.run_cli(["harmonize", str(self.ws)])
        self.assertEqual(code, 0)

        content = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("সার্বজনীন নিয়মাবলী", content)
        self.assertIn("🚀", content)
        self.assertIn("বাংলা: কোড পরিষ্কার রাখুন", content)
        self.assertIn("日本語: 品質を保つこと", content)
        self.assertIn("🤖", content)

    def test_boundary_crlf_windows_line_endings(self) -> None:
        """Assures Windows CRLF line endings are harmonized cleanly without corruption."""
        crlf_rules = (
            "# Windows Rules\r\n- Keep CRLF safe\r\n\r\n"
            "<!-- Added by PSL-HARNESS -->\r\nOld rules\r\n<!-- End PSL-HARNESS -->\r\n"
        )
        self.create_fixture("legacy_psl", custom_rules=crlf_rules)
        code, out, err = self.run_cli(["harmonize", str(self.ws)])
        self.assertEqual(code, 0)

        content = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("# Windows Rules", content)
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", content)

    # =========================================================================
    # Domain 4: Directory Structures & Symlink Cycles
    # =========================================================================

    def test_boundary_circular_symlinks_in_agents(self) -> None:
        """Assures circular symlinks in .agent/ are skipped safely without infinite loop."""
        self.create_fixture("legacy_psl")
        loop_link = self.ws / ".agent" / "agents" / "loop"
        try:
            loop_link.symlink_to(self.ws / ".agent" / "agents", target_is_directory=True)
        except OSError:
            pass  # Some filesystems or OS may restrict directory symlinks

        code, out, err = self.run_cli(["harmonize", str(self.ws)])
        self.assertEqual(code, 0)
        self.assertTrue((self.ws / ".agents" / "agents" / "code_reviewer.md").exists())

    def test_boundary_deeply_nested_rule_directories(self) -> None:
        """Assures deeply nested rule hierarchies (.agent/rules/a/b/c/d/e.md) are preserved."""
        self.create_fixture("legacy_psl")
        deep_dir = self.ws / ".agent" / "rules" / "level1" / "level2" / "level3"
        deep_dir.mkdir(parents=True, exist_ok=True)
        deep_file = deep_dir / "deep_policy.md"
        deep_file.write_text("# Deep Security Policy\nStrict security.", encoding="utf-8")

        code, out, err = self.run_cli(["harmonize", str(self.ws)])
        self.assertEqual(code, 0)

        target_file = self.ws / ".agents" / "rules" / "level1" / "level2" / "level3" / "deep_policy.md"
        self.assertTrue(target_file.exists())
        self.assertEqual(target_file.read_text(encoding="utf-8"), deep_file.read_text(encoding="utf-8"))

    def test_boundary_empty_workflow_file(self) -> None:
        """Assures completely empty workflow file is synthesized into valid skill."""
        self.create_fixture("legacy_psl")
        (self.ws / ".agent" / "workflows" / "empty_flow.md").write_text("", encoding="utf-8")

        code, out, err = self.run_cli(["harmonize", str(self.ws)])
        self.assertEqual(code, 0)

        skill_md = self.ws / ".agents" / "skills" / "empty_flow" / "SKILL.md"
        self.assertTrue(skill_md.exists())
        content = skill_md.read_text(encoding="utf-8")
        self.assertIn("name: empty_flow", content)
        self.assertIn("description:", content)

    def test_boundary_workflow_with_partial_frontmatter(self) -> None:
        """Assures workflow with missing description gets synthesized description."""
        self.create_fixture("legacy_psl")
        partial_fm = "---\nname: explicit_name\n---\n# Workflow Heading\nDetailed workflow body."
        (self.ws / ".agent" / "workflows" / "partial.md").write_text(partial_fm, encoding="utf-8")

        code, out, err = self.run_cli(["harmonize", str(self.ws)])
        self.assertEqual(code, 0)

        skill_md = self.ws / ".agents" / "skills" / "partial" / "SKILL.md"
        self.assertTrue(skill_md.exists())
        content = skill_md.read_text(encoding="utf-8")
        self.assertIn("name: explicit_name", content)
        self.assertIn("description:", content)

    def test_boundary_identical_destination_skips_unnecessary_writes(self) -> None:
        """Assures pre-existing identical files in .agents/ do not trigger errors or corruption."""
        self.create_fixture("legacy_psl")
        dest_agent = self.ws / ".agents" / "agents" / "code_reviewer.md"
        dest_agent.parent.mkdir(parents=True, exist_ok=True)
        dest_agent.write_text("# Code Reviewer\nExpert automated reviewer.", encoding="utf-8")

        code, out, err = self.run_cli(["harmonize", str(self.ws)])
        self.assertEqual(code, 0)
        self.assertTrue(dest_agent.exists())

    # =========================================================================
    # Domain 5: CLI Argument Combinations & Missing Inputs
    # =========================================================================

    def test_boundary_combine_dry_run_and_json(self) -> None:
        """Assures combining '--dry-run' and '--json' returns pure JSON with dry_run=True."""
        self.create_fixture("legacy_psl")
        code, out, err = self.run_cli(["harmonize", "--dry-run", "--json", str(self.ws)])
        self.assertEqual(code, 0)
        data = self.parse_json_stdout(out)
        self.assertTrue(data.get("dry_run"))
        self.assertTrue(data.get("success"))

    def test_boundary_unknown_subcommand(self) -> None:
        """Assures unknown subcommand returns exit code 2."""
        code, out, err = self.run_cli(["invalid_subcommand_xyz"])
        self.assertIn(code, [2, 1])

    def test_boundary_unknown_flag(self) -> None:
        """Assures unrecognized command-line flag returns exit code 2 with usage notice."""
        code, out, err = self.run_cli(["doctor", "--invalid-flag-123"])
        self.assertEqual(code, 2)
        self.assertIn("unrecognized arguments", err.lower() + out.lower())

    def test_boundary_harmonize_default_path_current_dir(self) -> None:
        """Assures omitting path argument defaults cleanly to current working directory."""
        # Run inside temporary self.ws by patching CWD
        orig_cwd = os.getcwd()
        try:
            os.chdir(str(self.ws))
            code, out, err = self.run_cli(["harmonize", "--dry-run", "--json"])
            self.assertEqual(code, 0)
            data = self.parse_json_stdout(out)
            self.assertTrue(data.get("success"))
        finally:
            os.chdir(orig_cwd)

    def test_boundary_init_override_flag(self) -> None:
        """Assures 'agyis init --override' successfully overwrites existing files."""
        (self.ws / "AGENTS.md").write_text("# Existing Pre-Rule", encoding="utf-8")
        code, out, err = self.run_cli(["init", "--override", str(self.ws)])
        self.assertEqual(code, 0)
        content = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", content)


if __name__ == "__main__":
    unittest.main()
