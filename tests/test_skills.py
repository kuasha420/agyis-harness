#!/usr/bin/env python3
"""
Hermetic unit tests for PSL Modular Skills (harness/skills).

Validates skill discovery, YAML frontmatter schemas, descriptions,
and filesystem synchronization between harness/skills and .agents/skills.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from harness.skills import (
    DEFAULT_SKILLS_DIR,
    DEFAULT_TARGET_DIR,
    SkillSpec,
    get_skill,
    list_skills,
    parse_frontmatter,
    sync_skills,
)


class TestModularSkills(unittest.TestCase):
    """Test suite for modular stack skills and registry operations."""

    EXPECTED_STACK_SKILLS = {
        "psl-stack-shell",
        "psl-stack-typescript",
        "psl-stack-python",
        "psl-stack-backend",
        "psl-stack-systems",
    }

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.isolated_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_list_skills_discovers_all_skills(self) -> None:
        """Every skill folder in harness/skills/ must contain a discoverable SKILL.md."""
        skills = list_skills()
        self.assertGreaterEqual(len(skills), 8)

        skill_names = {s.name for s in skills}
        for expected in self.EXPECTED_STACK_SKILLS:
            self.assertIn(
                expected,
                skill_names,
                f"Expected stack skill '{expected}' not found in registry",
            )

    def test_skill_schema_and_frontmatter_contracts(self) -> None:
        """Each skill must have valid name, non-empty description, and body content."""
        skills = list_skills()
        for skill in skills:
            with self.subTest(skill=skill.name):
                self.assertTrue(skill.name, "Skill name must not be empty")
                self.assertTrue(
                    skill.description,
                    f"Skill '{skill.name}' must have a non-empty description",
                )
                self.assertGreater(
                    len(skill.description),
                    20,
                    f"Skill '{skill.name}' description is suspiciously short",
                )
                self.assertTrue(
                    skill.path.exists(),
                    f"Skill file path {skill.path} does not exist",
                )
                self.assertTrue(
                    skill.body.strip(),
                    f"Skill '{skill.name}' must have non-empty markdown instructions",
                )

    def test_get_skill_lookup(self) -> None:
        """Skills must be retrievable by exact name, hyphen, or underscore variant."""
        shell_spec = get_skill("psl-stack-shell")
        self.assertIsNotNone(shell_spec)
        self.assertEqual(shell_spec.name, "psl-stack-shell")

        shell_spec_under = get_skill("psl_stack_shell")
        self.assertIsNotNone(shell_spec_under)
        self.assertEqual(shell_spec_under.name, "psl-stack-shell")

        non_existent = get_skill("non-existent-skill-xyz")
        self.assertIsNone(non_existent)

    def test_parse_frontmatter_folded_and_lists(self) -> None:
        """YAML frontmatter parser handles folded strings and basic data structures."""
        sample = (
            "---\n"
            "name: test-skill\n"
            "description: >-\n"
            "  This is line one.\n"
            "  This is line two.\n"
            "category: testing\n"
            "---\n"
            "# Content Body\n"
            "Instruction text here.\n"
        )
        fm, body = parse_frontmatter(sample)
        self.assertEqual(fm["name"], "test-skill")
        self.assertEqual(fm["description"], "This is line one. This is line two.")
        self.assertEqual(fm["category"], "testing")
        self.assertTrue(body.startswith("# Content Body"))

    def test_parse_frontmatter_empty_or_missing(self) -> None:
        """parse_frontmatter handles files without frontmatter gracefully."""
        plain = "# Just markdown\nNo frontmatter here."
        fm, body = parse_frontmatter(plain)
        self.assertEqual(fm, {})
        self.assertEqual(body, plain)

    def test_sync_skills_to_isolated_directory(self) -> None:
        """sync_skills copies all SKILL.md definitions to target directory."""
        target = self.isolated_path / "skills_target"
        synced = sync_skills(target_dir=target)

        self.assertGreaterEqual(len(synced), 8)
        for expected in self.EXPECTED_STACK_SKILLS:
            expected_file = target / expected / "SKILL.md"
            self.assertTrue(
                expected_file.exists(),
                f"Synced skill file {expected_file} was not created",
            )
            content = expected_file.read_text(encoding="utf-8")
            self.assertIn(f"name: {expected}", content)

    def test_agents_skills_mirror_in_sync(self) -> None:
        """The repository .agents/skills/ mirror must be in sync with harness/skills/."""
        source_skills = list_skills(DEFAULT_SKILLS_DIR)
        for skill in source_skills:
            mirrored = DEFAULT_TARGET_DIR / skill.path.parent.name / "SKILL.md"
            self.assertTrue(
                mirrored.exists(),
                f"Mirrored skill missing at {mirrored}",
            )
            # Verify contents are identical
            source_content = skill.path.read_text(encoding="utf-8")
            mirrored_content = mirrored.read_text(encoding="utf-8")
            self.assertEqual(
                source_content,
                mirrored_content,
                f"Mirrored skill at {mirrored} is out of sync with source {skill.path}",
            )


if __name__ == "__main__":
    unittest.main()
