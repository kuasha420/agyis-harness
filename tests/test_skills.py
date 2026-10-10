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

    def test_agents_rules_mirror_in_sync(self) -> None:
        """The repository .agents/rules/AGENTS.md mirror must be in sync with harness/rules/AGENTS.md."""
        repo_root = DEFAULT_SKILLS_DIR.parents[1]
        harness_rules = repo_root / "harness" / "rules" / "AGENTS.md"
        agents_rules = repo_root / ".agents" / "rules" / "AGENTS.md"
        self.assertTrue(harness_rules.exists(), f"Source rules missing at {harness_rules}")
        self.assertTrue(agents_rules.exists(), f"Mirrored rules missing at {agents_rules}")
        self.assertEqual(
            harness_rules.read_text(encoding="utf-8"),
            agents_rules.read_text(encoding="utf-8"),
            "Rule drift detected between harness/rules/AGENTS.md and .agents/rules/AGENTS.md",
        )

    def test_subagent_ladder_skill_contract(self) -> None:
        """subagent-ladder skill must be discoverable and declare 6-stage lifecycle and swarm invariants."""
        ladder = get_skill("subagent-ladder")
        self.assertIsNotNone(ladder, "subagent-ladder skill must be discoverable")
        self.assertEqual(ladder.name, "subagent-ladder")
        self.assertGreater(len(ladder.description), 30)

        # Invariants & lifecycle
        body = ladder.body
        self.assertIn("6-Stage Pipeline", body)
        self.assertIn("Anti-Bypass Invariant", body)
        self.assertIn("Multi-Node Swarm PR Ingestion Protocol", body)
        self.assertIn("gh pr list", body)

    def test_psl_test_runner_skills_contract(self) -> None:
        """Modular test runner skills (python, node, cargo, go) must satisfy discovery and instructions."""
        expected_runners = {
            "psl-test-python": ("Sub-Second Benchmark Invariant", "pytest"),
            "psl-test-node": ("vitest", "jest"),
            "psl-test-cargo": ("cargo test", "clippy"),
            "psl-test-go": ("go test", "-race"),
        }
        for runner_name, keywords in expected_runners.items():
            with self.subTest(runner=runner_name):
                spec = get_skill(runner_name)
                self.assertIsNotNone(spec, f"Test runner skill '{runner_name}' not found")
                self.assertEqual(spec.name, runner_name)
                self.assertGreater(len(spec.description), 25)
                for kw in keywords:
                    self.assertIn(
                        kw,
                        spec.body,
                        f"Expected keyword '{kw}' in '{runner_name}' body",
                    )

    def test_workstation_and_remote_modular_skills_contracts(self) -> None:
        """Workstation and remote modular skills must satisfy discovery, frontmatter, and empirical runbook contracts."""
        expected_skills = {
            "storage-ops": (
                "Bounded-Depth Disk Triage",
                "du -h",
                "pacman",
                "journalctl",
                "docker",
                "btrfs",
                "timeshift",
                "ntfs3",
            ),
            "audio-ops": (
                "wpctl",
                "pipewire",
                "wireplumber",
                "bluetoothctl",
                "loudnorm",
                "ffmpeg",
                "vlc",
            ),
            "display-ops": (
                "kscreen-doctor",
                "xdg-desktop-portal",
                "Wayland",
                "PipeWire",
                "ozone",
                "sunshine",
                "cap_sys_admin",
            ),
            "sec-forensics": (
                "docker run --rm -v /:/host:ro",
                "gcloud iam service-accounts keys delete",
                "remote script",
                "pdf",
            ),
            "media-ops": (
                "yt-dlp",
                "ffmpeg",
                "vflip",
                "hflip",
            ),
        }
        for skill_name, keywords in expected_skills.items():
            with self.subTest(skill=skill_name):
                spec = get_skill(skill_name)
                self.assertIsNotNone(spec, f"Modular skill '{skill_name}' not found")
                self.assertEqual(spec.name, skill_name)
                self.assertGreater(
                    len(spec.description),
                    30,
                    f"Skill '{skill_name}' description is suspiciously short",
                )
                for kw in keywords:
                    self.assertIn(
                        kw.lower(),
                        spec.body.lower(),
                        f"Expected keyword '{kw}' in '{skill_name}' body",
                    )


if __name__ == "__main__":
    unittest.main()

