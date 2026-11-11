#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic verification gate for in-tree skills deduplication.

Enforces that any skills present in .agents/skills/ that mirror harness/skills/
MUST be symlinks pointing to ../../harness/skills/<name> and cannot be
independent directory copies (preventing repository duplicate pollution).
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import unittest

from harness.runtime.hygiene_checks import check_in_tree_skills_symlinks

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestSkillsDedupGate(unittest.TestCase):
    """Test suite for in-tree skills deduplication verification gate."""

    def test_current_repo_skills_are_pure_symlinks(self) -> None:
        """Every skill in .agents/skills mirroring harness/skills must be a valid symlink."""
        result = check_in_tree_skills_symlinks(REPO_ROOT)
        self.assertEqual(
            result["status"],
            "PASS",
            f"In-tree skills deduplication gate failed in repository: {result.get('details')}",
        )
        self.assertGreater(result["checked"], 10, "Expected at least 10 in-tree mirrored skills to be checked")
        self.assertEqual(len(result["violations"]), 0)

        # Directly verify each mirrored skill entry on disk
        harness_skills = REPO_ROOT / "harness" / "skills"
        agents_skills = REPO_ROOT / ".agents" / "skills"

        for item in sorted(agents_skills.iterdir()):
            if item.name.startswith("."):
                continue
            mirror = harness_skills / item.name
            if mirror.is_dir() and (mirror / "SKILL.md").is_file():
                self.assertTrue(
                    item.is_symlink(),
                    f"Skill '{item.name}' in .agents/skills must be a symlink to harness/skills/{item.name}",
                )
                link_target = os.readlink(item)
                expected_rel = f"../../harness/skills/{item.name}"
                self.assertEqual(
                    link_target,
                    expected_rel,
                    f"Symlink for '{item.name}' must point to '{expected_rel}', got '{link_target}'",
                )
                self.assertEqual(item.resolve(), mirror.resolve())

    def test_gate_detects_physical_copy_violation(self) -> None:
        """Gate must fail if a mirrored skill is an independent directory copy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            h_skill = ws / "harness" / "skills" / "sample-skill"
            h_skill.mkdir(parents=True)
            (h_skill / "SKILL.md").write_text("# Sample Skill\n", encoding="utf-8")

            # Create physical directory copy in .agents/skills
            a_skill = ws / ".agents" / "skills" / "sample-skill"
            a_skill.mkdir(parents=True)
            (a_skill / "SKILL.md").write_text("# Copied Sample Skill\n", encoding="utf-8")

            result = check_in_tree_skills_symlinks(ws)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(len(result["violations"]), 1)
            self.assertEqual(result["violations"][0]["skill"], "sample-skill")
            self.assertIn("physical copy", result["violations"][0]["reason"])

    def test_gate_detects_wrong_symlink_target(self) -> None:
        """Gate must fail if a symlink points to an improper target path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            h_skill = ws / "harness" / "skills" / "sample-skill"
            h_skill.mkdir(parents=True)
            (h_skill / "SKILL.md").write_text("# Sample Skill\n", encoding="utf-8")

            a_dir = ws / ".agents" / "skills"
            a_dir.mkdir(parents=True)
            # Create symlink pointing elsewhere
            (a_dir / "sample-skill").symlink_to("../../other/path")

            result = check_in_tree_skills_symlinks(ws)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(len(result["violations"]), 1)
            self.assertIn("Symlink points to", result["violations"][0]["reason"])

    def test_gate_allows_custom_unmirrored_workspace_skills(self) -> None:
        """Gate permits legitimate custom repo-specific skills that do not exist in harness/skills."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            h_skill = ws / "harness" / "skills" / "core-skill"
            h_skill.mkdir(parents=True)
            (h_skill / "SKILL.md").write_text("# Core Skill\n", encoding="utf-8")

            a_dir = ws / ".agents" / "skills"
            a_dir.mkdir(parents=True)
            # Valid symlink for mirrored skill
            (a_dir / "core-skill").symlink_to("../../harness/skills/core-skill")
            # Custom workspace skill (not in harness/skills)
            custom_skill = a_dir / "my-custom-tool"
            custom_skill.mkdir()
            (custom_skill / "SKILL.md").write_text("# Custom Skill\n", encoding="utf-8")

            result = check_in_tree_skills_symlinks(ws)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["checked"], 1)
            self.assertEqual(len(result["violations"]), 0)

    def test_gate_detects_absolute_symlink_violation(self) -> None:
        """Gate must reject absolute symlinks to prevent machine-local non-portable paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            h_skill = ws / "harness" / "skills" / "sample-skill"
            h_skill.mkdir(parents=True)
            (h_skill / "SKILL.md").write_text("# Sample Skill\n", encoding="utf-8")

            a_dir = ws / ".agents" / "skills"
            a_dir.mkdir(parents=True)
            # Create absolute symlink (points to h_skill directly, which exists, but is absolute)
            (a_dir / "sample-skill").symlink_to(h_skill.resolve())

            result = check_in_tree_skills_symlinks(ws)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(len(result["violations"]), 1)
            self.assertIn("Symlink points to", result["violations"][0]["reason"])

    def test_gate_detects_broken_symlink_violation(self) -> None:
        """Gate must reject broken symlinks that point to deleted or non-existent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            h_skill = ws / "harness" / "skills" / "sample-skill"
            h_skill.mkdir(parents=True)
            (h_skill / "SKILL.md").write_text("# Sample Skill\n", encoding="utf-8")

            a_dir = ws / ".agents" / "skills"
            a_dir.mkdir(parents=True)
            # Create symlink pointing to expected relative path
            (a_dir / "sample-skill").symlink_to("../../harness/skills/sample-skill")
            # Now delete the harness skill directory to simulate a broken target
            shutil.rmtree(h_skill)
            # Create a dummy harness skill so harness/skills is recognized
            dummy = ws / "harness" / "skills" / "other-skill"
            dummy.mkdir(parents=True)
            (dummy / "SKILL.md").write_text("# Other\n", encoding="utf-8")

            # But wait: if sample-skill is in agents_skills and pointed to ../../harness/skills/sample-skill which is gone:
            # Let's see: sample-skill is NOT in harness_skills, so it won't be in harness_skills unless harness_skills had it.
            # If harness_skills has sample-skill as a file instead of directory:
            (ws / "harness" / "skills" / "sample-skill").write_text("not a dir", encoding="utf-8")

            # Or if sample-skill symlink in .agents/skills points to broken path:
            broken_skill = a_dir / "other-skill"
            broken_skill.symlink_to("../../harness/skills/nonexistent")

            result = check_in_tree_skills_symlinks(ws)
            self.assertEqual(result["status"], "FAIL")
    def test_gate_passes_on_non_harness_workspace(self) -> None:
        """Gate safely skips and passes on non-in-tree workspaces."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            result = check_in_tree_skills_symlinks(ws)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["checked"], 0)


if __name__ == "__main__":
    unittest.main()

