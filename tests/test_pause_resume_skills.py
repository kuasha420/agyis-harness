#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic contract tests for paired /pause and /resume modular skills.

Verifies discovery, relative symlink hygiene, platform size caps,
Table of Contents anchor validity, Zero-Kill / pause_gate.json alignment,
mandatory live-first /resume Step 1 ordering + 3-branch triage,
and backwards-compatible preset registration.
"""

from __future__ import annotations

import importlib.resources as ir
import os
from pathlib import Path
import re
import tempfile
import unittest

from harness.hooks.command_safety_hook import PAUSE_GATE_FILES
from harness.skills import (
    DEFAULT_SKILLS_DIR,
    DEFAULT_TARGET_DIR,
    GROUP_PRESETS,
    get_skill,
    list_skills,
    parse_frontmatter,
    resolve_skills_to_sync,
    sync_skills,
)

PLATFORM_SKILL_MAX_BYTES = 24576


def _gfm_heading_slug(text: str) -> str:
    """Compute a GitHub-Flavored Markdown heading anchor slug."""
    cleaned = re.sub(r"[^\w\s-]", "", text.strip().lower())
    return re.sub(r"\s", "-", cleaned)


def _extract_markdown_headings(lines: list[str]) -> list[tuple[int, int, str, str]]:
    """Return (line_idx, level, text, slug) for ATX headings outside fenced code blocks."""
    headings: list[tuple[int, int, str, str]] = []
    in_fence = False
    fence_char = ""
    slug_counts: dict[str, int] = {}

    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_char = marker
            elif marker == fence_char:
                in_fence = False
                fence_char = ""
            continue
        if in_fence:
            continue

        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            continue
        level = len(match.group(1))
        raw_text = re.sub(r"\s+#+\s*$", "", match.group(2)).strip()
        base_slug = _gfm_heading_slug(raw_text)
        seen = slug_counts.get(base_slug, 0) + 1
        slug_counts[base_slug] = seen
        slug = base_slug if seen == 1 else f"{base_slug}-{seen - 1}"
        headings.append((idx, level, raw_text, slug))

    return headings


class TestPauseAndResumeSkills(unittest.TestCase):
    """Contract and behavioral verification for harness/skills/{pause,resume}."""

    def test_discovery_frontmatter_and_package_resources(self) -> None:
        """list_skills() and get_skill() discover pause and resume with valid frontmatter and package resources."""
        discovered = {spec.name: spec for spec in list_skills()}
        for skill_name in ("pause", "resume"):
            with self.subTest(skill=skill_name):
                self.assertIn(skill_name, discovered)
                spec = get_skill(skill_name)
                self.assertIsNotNone(spec)
                assert spec is not None
                self.assertEqual(spec.name, skill_name)
                self.assertGreater(len(spec.description), 40)

                raw = spec.path.read_text(encoding="utf-8")
                fm, body = parse_frontmatter(raw)
                self.assertEqual(fm.get("name"), skill_name)
                self.assertEqual(fm.get("description"), spec.description)
                self.assertTrue(body.strip())

                pkg_file = ir.files("harness.skills") / skill_name / "SKILL.md"
                self.assertTrue(pkg_file.is_file(), f"{skill_name}/SKILL.md must be accessible via importlib.resources")

    def test_relative_symlinks_resolve_to_harness_sources(self) -> None:
        """.agents/skills/{pause,resume} must be relative symlinks pointing to ../../harness/skills/{pause,resume}."""
        for skill_name in ("pause", "resume"):
            with self.subTest(skill=skill_name):
                link_path = DEFAULT_TARGET_DIR / skill_name
                expected_source = (DEFAULT_SKILLS_DIR / skill_name).resolve()

                self.assertTrue(link_path.is_symlink(), f"{link_path} must be a symlink")
                self.assertEqual(os.readlink(link_path), f"../../harness/skills/{skill_name}")
                self.assertEqual(link_path.resolve(), expected_source)

                source_md = expected_source / "SKILL.md"
                mirrored_md = link_path / "SKILL.md"
                self.assertTrue(mirrored_md.is_file())
                self.assertEqual(
                    source_md.read_text(encoding="utf-8"),
                    mirrored_md.read_text(encoding="utf-8"),
                )

    def test_size_cap_and_table_of_contents_integrity(self) -> None:
        """Both pause and resume SKILL.md stay strictly < 24,576 bytes with valid ToC anchors when > 100 lines."""
        for skill_name in ("pause", "resume"):
            with self.subTest(skill=skill_name):
                skill_md = DEFAULT_SKILLS_DIR / skill_name / "SKILL.md"
                size = skill_md.stat().st_size
                self.assertLess(size, PLATFORM_SKILL_MAX_BYTES)

                lines = skill_md.read_text(encoding="utf-8").splitlines()
                if len(lines) > 100:
                    headings = _extract_markdown_headings(lines)
                    toc_entries = [h for h in headings if h[1] == 2 and h[2] == "Table of Contents"]
                    self.assertEqual(len(toc_entries), 1)

                    toc_start = toc_entries[0][0] + 1
                    toc_end = len(lines)
                    for idx in range(toc_start, len(lines)):
                        stripped = lines[idx].strip()
                        if stripped == "---" or stripped.startswith("## "):
                            toc_end = idx
                            break

                    toc_block = "\n".join(lines[toc_start:toc_end])
                    anchors = re.findall(r"\[[^\]]+\]\(#([^)\s]+)\)", toc_block)
                    self.assertGreater(len(anchors), 0)

                    all_slugs = {h[3] for h in headings}
                    for anchor in anchors:
                        self.assertIn(anchor, all_slugs)

                    h2_slugs = {h[3] for h in headings if h[1] == 2 and h[2] != "Table of Contents"}
                    self.assertEqual(sorted(h2_slugs - set(anchors)), [])

    def test_pause_skill_enforces_zero_kill_gate_and_handshake(self) -> None:
        """pause/SKILL.md enforces Zero-Kill, PAUSE_GATE_FILES alignment, roster inspection, handshake, and checkpoint."""
        spec = get_skill("pause")
        self.assertIsNotNone(spec)
        assert spec is not None
        body = spec.body

        # Alignment with command_safety_hook.PAUSE_GATE_FILES
        gate_strings = {p.as_posix() for p in PAUSE_GATE_FILES}
        self.assertIn(".agents/artifacts/pause_gate.json", gate_strings)
        self.assertIn(".agents/artifacts/PARKED_STATE.md", gate_strings)

        required_tokens = (
            "Zero-Kill",
            ".agents/artifacts/pause_gate.json",
            '"status": "pausing"',
            '"status": "paused"',
            "PARKED_STATE.md",
            "manage_subagents(Action='list')",
            "swarm(action='status')",
            "manage_task(Action='list')",
            "agyis subagents --liveness",
            "[DIRECTIVE: PAUSE_EXECUTION]",
            "send_message",
            "[PARK_ACK: <UUID>]",
            "agyis checkpoint create",
            "/resume",
            "swarm(action='kill')",
            "pkill -9",
        )
        for token in required_tokens:
            self.assertIn(token, body, f"pause/SKILL.md missing required token: {token}")

        # Verify state transition order: pausing gate declared before finalized paused state
        pausing_pos = body.index('"status": "pausing"')
        paused_pos = body.index('"status": "paused"')
        self.assertLess(pausing_pos, paused_pos)

    def test_resume_skill_enforces_mandatory_step1_and_three_branch_triage(self) -> None:
        """resume/SKILL.md mandates live roster audit before spawning/gate removal and codifies 3-branch triage."""
        spec = get_skill("resume")
        self.assertIsNotNone(spec)
        assert spec is not None
        body = spec.body

        required_tokens = (
            "manage_subagents(Action='list')",
            "manage_task(Action='list')",
            "agyis subagents --liveness",
            "agyis checkpoint status",
            "running",
            "ACTIVE",
            "double-spawn",
            "idle",
            "errored",
            "429",
            "[DIRECTIVE: RESUME_EXECUTION]",
            "send_message",
            "DEAD",
            "powerloss-resume",
            ".git/index.lock",
            "git status -s",
            "git diff",
            ".agents/teamwork/backups/",
            "REPLACEMENT_BRIEF.md",
            "agyis clean",
            ".agents/artifacts/pause_gate.json",
        )
        for token in required_tokens:
            self.assertIn(token, body, f"resume/SKILL.md missing required token: {token}")

        # Verify strict ordering: Step 1 discovery section precedes Step 2 triage and Step 3 gate removal
        step1_pos = body.index("## 2. Step 1")
        step2_pos = body.index("## 3. Step 2")
        step3_pos = body.index("## 4. Step 3")
        self.assertLess(step1_pos, step2_pos)
        self.assertLess(step2_pos, step3_pos)

        step1_section = body[step1_pos:step2_pos]
        for first_call in (
            "manage_subagents(Action='list')",
            "manage_task(Action='list')",
            "agyis subagents --liveness",
            "agyis checkpoint status",
        ):
            self.assertIn(first_call, step1_section, f"Step 1 must explicitly invoke {first_call}")

        step2_section = body[step2_pos:step3_pos]
        branch1_pos = step2_section.index("### Branch 1:")
        branch2_pos = step2_section.index("### Branch 2:")
        branch3_pos = step2_section.index("### Branch 3:")
        self.assertLess(branch1_pos, branch2_pos)
        self.assertLess(branch2_pos, branch3_pos)

        # Verify Branch 3 enforces backup & REPLACEMENT_BRIEF.md before spawning replacement
        branch3_section = step2_section[branch3_pos:]
        self.assertIn(".git/index.lock", branch3_section)
        self.assertIn("git diff", branch3_section)
        self.assertIn("REPLACEMENT_BRIEF.md", branch3_section)
        self.assertLess(
            branch3_section.index("git diff"),
            branch3_section.index("Spawn Replacement Only After Snapshot"),
        )

    def test_presets_backwards_compatibility_and_pause_resume_group_sync(self) -> None:
        """resilience and continuity presets stay untouched while pause-resume resolves and syncs all 4 skills."""
        self.assertEqual(
            GROUP_PRESETS["resilience"],
            ["powerloss-resume", "db-ops", "storage-ops"],
        )
        self.assertEqual(
            GROUP_PRESETS["continuity"],
            ["graceful-parking", "milestone-handoff", "git-worktree-ops", "crosstalk"],
        )
        self.assertEqual(
            GROUP_PRESETS["pause-resume"],
            ["pause", "resume", "graceful-parking", "powerloss-resume"],
        )
        self.assertEqual(
            resolve_skills_to_sync(group="pause-resume"),
            ["pause", "resume", "graceful-parking", "powerloss-resume"],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / ".agents" / "skills"
            synced = sync_skills(target_dir=dest, group="pause-resume")
            self.assertEqual(len(synced), 4)
            for skill_name in ("pause", "resume", "graceful-parking", "powerloss-resume"):
                skill_file = dest / skill_name / "SKILL.md"
                self.assertTrue(skill_file.is_file(), f"Expected synced skill at {skill_file}")
                fm, _ = parse_frontmatter(skill_file.read_text(encoding="utf-8"))
                self.assertEqual(fm.get("name"), skill_name)


if __name__ == "__main__":
    unittest.main()
