#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Hermetic unit tests for Track 1 (WS1) workspace AGENTS.md injection and .agent/ rewriting."""

from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import unittest

from harness.delivery.constants import REPO_ROOT
from harness.delivery.harmonize import _rewrite_legacy_agent_references
from harness.delivery.rules_inject import (
    PLUGIN_INHERITANCE_POINTER,
    TAG_END,
    TAG_START,
    filter_universal_rules_for_workspace,
    inject_tagged_block_clean,
    relocate_custom_tagged_sections,
    strip_yaml_frontmatter,
)


def _assert_prettier_clean(test_case: unittest.TestCase, text: str) -> None:
    """Asserts core Prettier Markdown formatting invariants on injected text."""
    test_case.assertTrue(text.endswith("\n"))
    test_case.assertFalse(text.endswith("\n\n"))
    test_case.assertNotIn("\r", text)
    test_case.assertNotIn("\n\n\n", text)
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        test_case.assertEqual(line, line.rstrip(" \t"), f"Trailing space on line {idx + 1}: {line!r}")
        test_case.assertFalse(
            re.match(r"^#{1,6}\s*<!--\s*(?:Added by|End)\s+(?:AGYIS|PSL)-HARNESS", line),
            f"Malformed heading+marker collision on line {idx + 1}: {line!r}",
        )
    # Blank lines around headings and fenced code blocks
    in_fence = False
    for idx, line in enumerate(lines):
        if line.startswith("```"):
            if not in_fence:
                if idx > 0:
                    test_case.assertEqual(lines[idx - 1], "", f"Missing blank line before code fence at {idx + 1}")
                in_fence = True
            else:
                if idx + 1 < len(lines):
                    test_case.assertEqual(lines[idx + 1], "", f"Missing blank line after code fence at {idx + 1}")
                in_fence = False
            continue
        if not in_fence and re.match(r"^#{1,6}\s+\S", line):
            if idx > 0:
                test_case.assertEqual(lines[idx - 1], "", f"Missing blank line before heading at {idx + 1}")
            if idx + 1 < len(lines):
                test_case.assertEqual(lines[idx + 1], "", f"Missing blank line after heading at {idx + 1}")


class TestStripYamlFrontmatter(unittest.TestCase):
    """Tests for YAML frontmatter stripping."""

    def test_strips_standard_frontmatter_and_crlf_bom(self) -> None:
        raw = "\ufeff---\r\ntrigger: manual\r\ndescription: Template\r\n---\r\n\r\n# Title\r\nBody\r\n"
        stripped = strip_yaml_frontmatter(raw)
        self.assertEqual(stripped, "# Title\nBody\n")
        self.assertNotIn("trigger: manual", stripped)

    def test_preserves_markdown_horizontal_rules(self) -> None:
        raw = "---\n\n# Heading\n\nParagraph\n\n---\n"
        self.assertEqual(strip_yaml_frontmatter(raw), raw)

    def test_preserves_unclosed_frontmatter(self) -> None:
        raw = "---\ntrigger: manual\n# No closing fence\n"
        self.assertEqual(strip_yaml_frontmatter(raw), raw)


class TestFilterUniversalRulesForWorkspace(unittest.TestCase):
    """Tests stack-aware CLI filtering, global-rule dedup, and Prettier hygiene."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name)
        self.template = (REPO_ROOT / "harness" / "rules" / "universal_agents.md").read_text(
            encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_pure_typescript_repo_omits_python_aff_and_rea_verify(self) -> None:
        (self.ws / "package.json").write_text('{"name": "ts-app"}', encoding="utf-8")
        # Python files inside ignored directories must not trigger agyis audit aff
        (self.ws / "node_modules" / "pkg").mkdir(parents=True)
        (self.ws / "node_modules" / "pkg" / "setup.py").write_text("x = 1\n", encoding="utf-8")
        (self.ws / ".venv" / "lib").mkdir(parents=True)
        (self.ws / ".venv" / "lib" / "site.py").write_text("x = 1\n", encoding="utf-8")

        filtered = filter_universal_rules_for_workspace(
            self.template, self.ws, stacks=["typescript"], rea_enabled=False
        )
        self.assertNotIn("trigger: manual", filtered)
        self.assertIn(PLUGIN_INHERITANCE_POINTER, filtered)
        self.assertNotIn("PSL-INV-001)", filtered)
        self.assertNotIn("PSL-RE-001", filtered)
        self.assertNotIn("agyis audit aff", filtered)
        self.assertNotIn("agyis verify --spec", filtered)
        self.assertNotIn("agyis verify ", filtered)
        self.assertIn("agyis test --diff", filtered)
        self.assertIn("agyis test --full", filtered)
        self.assertIn("_Explicit CLI palettes yield 10x lower human intervention rates:_", filtered)
        _assert_prettier_clean(self, filtered)

    def test_python_repo_retains_audit_aff_only(self) -> None:
        (self.ws / "src").mkdir()
        (self.ws / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")

        filtered = filter_universal_rules_for_workspace(self.template, self.ws)
        self.assertIn("agyis audit aff", filtered)
        self.assertNotIn("agyis verify --spec", filtered)
        self.assertNotIn("agyis verify ", filtered)
        _assert_prettier_clean(self, filtered)

    def test_specs_ledger_or_rea_retains_verify_commands(self) -> None:
        # Case 1: explicit rea_enabled=True
        res_flag = filter_universal_rules_for_workspace(
            self.template, self.ws, stacks=["rust"], rea_enabled=True
        )
        self.assertIn("agyis verify --spec", res_flag)
        self.assertIn("agyis verify ", res_flag)
        self.assertNotIn("agyis audit aff", res_flag)

        # Case 2: docs/specs directory
        ws_specs = self.ws / "specs_repo"
        (ws_specs / "docs" / "specs").mkdir(parents=True)
        res_specs = filter_universal_rules_for_workspace(self.template, ws_specs)
        self.assertIn("agyis verify --spec", res_specs)
        self.assertIn("agyis verify ", res_specs)

        # Case 3: .agents/ledger directory
        ws_ledger = self.ws / "ledger_repo"
        (ws_ledger / ".agents" / "ledger").mkdir(parents=True)
        res_ledger = filter_universal_rules_for_workspace(self.template, ws_ledger)
        self.assertIn("agyis verify --spec", res_ledger)
        self.assertIn("agyis verify ", res_ledger)

        # Case 4: .agyis/config.json experimental_rea=True
        ws_cfg = self.ws / "cfg_repo"
        (ws_cfg / ".agyis").mkdir(parents=True)
        (ws_cfg / ".agyis" / "config.json").write_text(json.dumps({"experimental_rea": True}), encoding="utf-8")
        res_cfg = filter_universal_rules_for_workspace(self.template, ws_cfg)
        self.assertIn("agyis verify --spec", res_cfg)

    def test_strips_legacy_codex_duplication_and_normalizes_italics(self) -> None:
        legacy_template = (
            "---\ntrigger: manual\n---\n\n"
            "# Universal Empirical Agent Rules: PSL Invariant Codex v2\n\n"
            "## 1. Explicit Project Command Dictionary (The Victory Pattern)\n\n"
            "*Explicit CLI palettes* keep `*.py` safe.\n\n"
            "```bash\n"
            "agyis test --diff\n"
            "agyis audit aff\n"
            "```\n\n"
            "---\n\n"
            "## 2. Empirical Verification & Clean-Room Testing (PSL-INV-001)\n\n"
            "1. Duplicated global rule.\n\n"
            "> **On-Demand Domain Pack — Cleanroom RE (`PSL-RE-001`)**: load re-ops.\n"
        )
        filtered = filter_universal_rules_for_workspace(legacy_template, self.ws, stacks=["typescript"])
        self.assertIn(PLUGIN_INHERITANCE_POINTER, filtered)
        self.assertIn("_Explicit CLI palettes_ keep `*.py` safe.", filtered)
        self.assertNotIn("Duplicated global rule.", filtered)
        self.assertNotIn("PSL-RE-001", filtered)
        self.assertNotIn("agyis audit aff", filtered)
        _assert_prettier_clean(self, filtered)


class TestRelocateAndInjectTaggedBlock(unittest.TestCase):
    """Tests custom section relocation and malformed fence repair."""

    def test_relocates_mi34_custom_sections_and_keeps_standard_discarded(self) -> None:
        legacy_inner = (
            "---\ntrigger: manual\n---\n\n"
            "## 1. Explicit Project Command Dictionary (The Victory Pattern)\n\n"
            "```bash\n"
            "## heading comment inside bash must not split\n"
            "cargo test\n"
            "```\n\n"
            "---\n\n"
            "## 2. Empirical Verification & Clean-Room Testing (PSL-INV-001)\n\n"
            "- Standard global rule.\n\n"
            "---\n\n"
            "## 2.1 Oracle Grounding Invariant\n\n"
            "- Every register offset must cite datasheet hardware docs.\n\n"
            "---\n\n"
            "## Hardware Probe Tests\n\n"
            "```bash\n"
            "cargo test --test live_hardware -- --ignored\n"
            "```\n"
        )
        remaining, relocated = relocate_custom_tagged_sections(legacy_inner)
        self.assertNotIn("Oracle Grounding Invariant", remaining)
        self.assertNotIn("live_hardware", remaining)
        self.assertEqual(len(relocated), 2)
        self.assertTrue(relocated[0].startswith("## 2.1 Oracle Grounding Invariant"))
        self.assertIn("datasheet hardware docs", relocated[0])
        self.assertFalse(relocated[0].endswith("---"))
        self.assertTrue(relocated[1].startswith("## Hardware Probe Tests"))
        self.assertIn("cargo test --test live_hardware -- --ignored", relocated[1])

    def test_repairs_purrmission_heading_marker_and_relocates_idempotently(self) -> None:
        existing = (
            "# Purrmission Codex Guide\n\n"
            "- Follow strict queue hygiene.\n\n"
            "## <!-- Added by AGYIS-HARNESS -->\n"
            "trigger: manual\n"
            "description: Template\n"
            "---\n\n"
            "## 2. Empirical Verification & Clean-Room Testing (PSL-INV-001)\n\n"
            "- Duplicate.\n\n"
            "## 2.1 Oracle Grounding Invariant\n\n"
            "- Keep this repo rule.\n"
            "<!-- End AGYIS-HARNESS -->\n"
        )
        slim_body = (
            "<!-- SPDX-License-Identifier: Apache-2.0 -->\n\n"
            f"{PLUGIN_INHERITANCE_POINTER}\n\n"
            "## Explicit Project Command Dictionary\n\n"
            "```bash\n"
            "pnpm test\n"
            "```\n"
        )
        updated = inject_tagged_block_clean(existing, slim_body)
        self.assertNotIn("## <!-- Added by AGYIS-HARNESS -->", updated)
        self.assertNotIn("trigger: manual", updated)
        self.assertNotIn("Duplicate.", updated)
        self.assertIn(f"\n\n{TAG_START}\n\n", updated)
        self.assertIn(f"\n\n{TAG_END}\n\n## 2.1 Oracle Grounding Invariant", updated)
        self.assertGreater(
            updated.index("## 2.1 Oracle Grounding Invariant"),
            updated.index(TAG_END),
        )
        _assert_prettier_clean(self, updated)

        # Second injection must not duplicate relocated sections
        second = inject_tagged_block_clean(updated, slim_body)
        self.assertEqual(second, updated)
        self.assertEqual(second.count("## 2.1 Oracle Grounding Invariant"), 1)


class TestRewriteLegacyAgentReferences(unittest.TestCase):
    """Tests bare .agent/ and .agent prose rewriting without false positives."""

    def test_rewrites_bare_agent_paths_and_prose_safely(self) -> None:
        sample = (
            "1. See `.agent/` and `.agent` directory.\n"
            "2. Check .agent/foo/bar.md and ../.agent/workflows/ci.md.\n"
            "3. Link: [Guide](.agent/rules/README.md) or (.agent) and .agent.\n"
            "4. Preserve .agents/, .agents/rules/keep.md, user-agent, and api.agent.json.\n"
        )
        rewritten = _rewrite_legacy_agent_references(sample)
        self.assertIn("`.agents/` and `.agents` directory.", rewritten)
        self.assertIn("Check .agents/foo/bar.md and ../.agents/workflows/ci.md.", rewritten)
        self.assertIn("[Guide](.agents/rules/README.md) or (.agents) and .agents.", rewritten)
        self.assertIn(".agents/, .agents/rules/keep.md, user-agent, and api.agent.json.", rewritten)
        self.assertNotIn(".agentss", rewritten)


if __name__ == "__main__":
    unittest.main()
