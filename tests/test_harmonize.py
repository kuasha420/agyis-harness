#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic unit and integration tests for Workspace Harmonization Engine & CLI (Milestone 4 Feature 15).

Comprehensive coverage:
1. Rule Fencing: Dual-tag matching, surrounding user rules preservation, regex escapes,
   multilingual Unicode & emojis, malformed fences (empty, mismatched, unclosed), CRLF endings,
   and multi-iteration convergence.
2. .agent to .agents Migration: Subagents, symlink guard, workflows to skills, deeply nested rules,
   root workflows directory, and idempotent write suppression.
3. Frontmatter Synthesis: Missing frontmatter, valid frontmatter preservation, leading blockquotes,
   markdown headings, double quote escaping, empty bodies, and partial frontmatter.
4. Dry-Run Isolation: Zero filesystem mutations, SHA-256 tree stability, .agents/ directory absence,
   and read-only permissions tolerance.
5. JSON Output Purity: Schema completeness (11 fields), pure JSON stdout guarantee, stderr isolation
   for PSL deprecation warnings, and failure exit codes.
6. Explicit Command Dictionary Extraction: Node, Python, Makefile extraction in harmonize,
   Section 1 injection, and error resilience on corrupted manifests.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from harness.cli import main
from harness.delivery.constants import REPO_ROOT
from harness.delivery.harmonize import (
    HarmonizeResult,
    harmonize_workspace,
    synthesize_skill_frontmatter,
)
from harness.delivery.workspace import (
    LEGACY_TAG_END,
    LEGACY_TAG_START,
    TAG_END,
    TAG_START,
    TAGGED_BLOCK_PATTERN,
    extract_command_dictionary,
    format_command_dictionary,
)


def hash_directory_tree(directory: Path) -> dict[str, str]:
    """Computes a SHA256 digest of all files in a directory tree."""
    hashes = {}
    if not directory.exists():
        return hashes
    for root, _, files in os.walk(directory):
        for f in sorted(files):
            p = Path(root) / f
            try:
                rel = str(p.relative_to(directory))
                hashes[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
            except OSError:
                pass
    return hashes


class TestHarmonizeEngine(unittest.TestCase):
    """Hermetic unit tests for harmonize_workspace and frontmatter synthesis."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # --- Frontmatter Synthesis Tests ---

    def test_synthesize_skill_frontmatter_missing_fm(self) -> None:
        content = "# Code Review\nExecute automated review checklist."
        res = synthesize_skill_frontmatter(content, default_name="review")
        self.assertTrue(res.startswith("---\nname: review\n"))
        self.assertIn('description: "Execute automated review checklist."', res)
        self.assertIn("# Code Review", res)

    def test_synthesize_skill_frontmatter_preserves_valid_fm(self) -> None:
        content = "---\nname: custom\ndescription: Custom skill\n---\n# Custom Body"
        res = synthesize_skill_frontmatter(content, default_name="fallback")
        self.assertEqual(res, content)

    def test_synthesize_skill_frontmatter_leading_blockquote_and_bullets(self) -> None:
        content = "> Standard deployment runbook for staging.\n> Second line.\n\nDeploy command."
        res = synthesize_skill_frontmatter(content, default_name="deploy")
        self.assertIn('description: "Standard deployment runbook for staging."', res)
        self.assertIn("name: deploy", res)

    def test_synthesize_skill_frontmatter_markdown_headings_skipped(self) -> None:
        content = "# Main Header\n\n## Subheader\n\n### Detail\n\nActual operational sentence."
        res = synthesize_skill_frontmatter(content, default_name="heading-skip")
        self.assertIn('description: "Actual operational sentence."', res)

    def test_synthesize_skill_frontmatter_double_quotes_escaped(self) -> None:
        content = 'Run the "golden" path test suite.'
        res = synthesize_skill_frontmatter(content, default_name="quote-test")
        self.assertIn(r'description: "Run the \"golden\" path test suite."', res)

    def test_synthesize_skill_frontmatter_empty_body(self) -> None:
        res = synthesize_skill_frontmatter("", default_name="empty-wf")
        self.assertIn("name: empty-wf", res)
        self.assertIn('description: "Migrated workflow: empty-wf"', res)

    def test_synthesize_skill_frontmatter_partial_frontmatter_missing_desc(self) -> None:
        content = "---\nname: custom-wf\n---\nFirst operational sentence."
        res = synthesize_skill_frontmatter(content, default_name="fallback-wf")
        self.assertIn("name: custom-wf", res)
        self.assertIn('description: "First operational sentence."', res)

    # --- Core Harmonization & Migration Tests ---

    def test_live_migration_copies_and_synthesizes(self) -> None:
        agent_dir = self.ws / ".agent"
        (agent_dir / "agents").mkdir(parents=True)
        (agent_dir / "agents" / "bot.md").write_text("# Bot", encoding="utf-8")

        (agent_dir / "workflows").mkdir(parents=True)
        (agent_dir / "workflows" / "ci.md").write_text(
            "# CI Pipeline\nRuns continuous integration.", encoding="utf-8"
        )

        (agent_dir / "rules").mkdir(parents=True)
        (agent_dir / "rules" / "standards.md").write_text("# Standards", encoding="utf-8")

        res = harmonize_workspace(self.ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        self.assertFalse(res.dry_run)
        self.assertTrue(res.modified)

        # Assert destination files exist
        self.assertTrue((self.ws / ".agents" / "agents" / "bot.md").is_file())
        self.assertTrue((self.ws / ".agents" / "skills" / "ci" / "SKILL.md").is_file())
        self.assertTrue((self.ws / ".agents" / "rules" / "standards.md").is_file())
        self.assertTrue((self.ws / "AGENTS.md").is_file())

        ci_content = (self.ws / ".agents" / "skills" / "ci" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("name: ci", ci_content)
        self.assertIn("description:", ci_content)

    def test_migration_ignores_circular_symlinks(self) -> None:
        agent_dir = self.ws / ".agent" / "agents"
        agent_dir.mkdir(parents=True)
        (agent_dir / "real.md").write_text("# Real Agent", encoding="utf-8")

        sym_agent = agent_dir / "symlink_agent.md"
        try:
            sym_agent.symlink_to(agent_dir / "real.md")
        except OSError:
            pass

        res = harmonize_workspace(self.ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        self.assertTrue((self.ws / ".agents" / "agents" / "real.md").is_file())
        self.assertFalse((self.ws / ".agents" / "agents" / "symlink_agent.md").exists())

    def test_migration_preserves_deeply_nested_rules(self) -> None:
        agent_dir = self.ws / ".agent"
        rules_dir = agent_dir / "rules" / "deep" / "level1" / "level2" / "level3"
        rules_dir.mkdir(parents=True)
        (rules_dir / "ultra_deep.md").write_text("# Deep Rule", encoding="utf-8")

        res = harmonize_workspace(self.ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        migrated = self.ws / ".agents" / "rules" / "deep" / "level1" / "level2" / "level3" / "ultra_deep.md"
        self.assertTrue(migrated.is_file())
        self.assertEqual(migrated.read_text(encoding="utf-8"), "# Deep Rule")

    def test_migration_root_workflows_directory(self) -> None:
        (self.ws / "workflows").mkdir(parents=True)
        (self.ws / "workflows" / "deploy.md").write_text(
            "# Deploy\nDeploys the application.", encoding="utf-8"
        )

        res = harmonize_workspace(self.ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        target_skill = self.ws / ".agents" / "skills" / "deploy" / "SKILL.md"
        self.assertTrue(target_skill.is_file())
        self.assertIn("name: deploy", target_skill.read_text(encoding="utf-8"))

    def test_migration_identical_destination_skips_unnecessary_writes(self) -> None:
        agent_dir = self.ws / ".agent" / "agents"
        agent_dir.mkdir(parents=True)
        (agent_dir / "helper.md").write_text("# Helper", encoding="utf-8")

        # Pre-create identical destination
        dest_dir = self.ws / ".agents" / "agents"
        dest_dir.mkdir(parents=True)
        (dest_dir / "helper.md").write_text("# Helper", encoding="utf-8")

        res = harmonize_workspace(self.ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        self.assertNotIn("helper.md", res.legacy_agents_migrated)

    # --- Rule Fencing Tests ---

    def test_tagged_rules_migration_preserves_custom_rules(self) -> None:
        agents_md = self.ws / "AGENTS.md"
        agents_md.write_text(
            "# Company Invariants\n- Do not break prod\n\n<!-- Added by PSL-HARNESS -->\nLegacy Invariants\n<!-- End PSL-HARNESS -->\n\n# Post Rules\n- Clean up\n",
            encoding="utf-8",
        )

        res = harmonize_workspace(self.ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        self.assertEqual(res.rules_action, "migrated_tagged_block")

        updated = agents_md.read_text(encoding="utf-8")
        self.assertIn("# Company Invariants\n- Do not break prod", updated)
        self.assertIn("# Post Rules\n- Clean up", updated)
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", updated)
        self.assertIn("<!-- End AGYIS-HARNESS -->", updated)
        self.assertNotIn("PSL-HARNESS", updated)

    def test_rule_fencing_surrounding_user_rules_prefix_and_suffix(self) -> None:
        prefix = "# Header Rules\n\nRule A: Be fast.\n\n"
        legacy_block = f"{LEGACY_TAG_START}\n# Old PSL Rules\nDo things the PSL way.\n{LEGACY_TAG_END}"
        suffix = "\n\n# Footer Rules\n\nRule Z: Be kind.\n"

        agents_file = self.ws / "AGENTS.md"
        agents_file.write_text(prefix + legacy_block + suffix, encoding="utf-8")

        res = harmonize_workspace(self.ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        self.assertEqual(res.rules_action, "migrated_tagged_block")

        updated = agents_file.read_text(encoding="utf-8")
        self.assertTrue(updated.startswith(prefix))
        self.assertTrue(updated.endswith(suffix))
        self.assertIn(TAG_START, updated)
        self.assertIn(TAG_END, updated)
        self.assertNotIn(LEGACY_TAG_START, updated)
        self.assertEqual(updated.count(TAG_START), 1)
        self.assertEqual(updated.count(TAG_END), 1)

    def test_rule_fencing_regex_backreferences_and_escapes(self) -> None:
        adversarial_user_rules = (
            "# Regex Rules\n\n"
            "Pattern: `r'([a-z]+)\\g<1>\\\\1\\\\0\\\\99$1(?P<id>\\d+)'`\n"
            "Format string: `\\U0001F600 \\x41 \\n \\t`\n"
            "Backslash path: `C:\\Users\\default\\AppData\\Local\\Temp`\n"
        )
        agents_file = self.ws / "AGENTS.md"
        agents_file.write_text(
            adversarial_user_rules + f"\n\n{LEGACY_TAG_START}\nold\n{LEGACY_TAG_END}\n",
            encoding="utf-8",
        )

        res = harmonize_workspace(self.ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        updated = agents_file.read_text(encoding="utf-8")
        self.assertIn(adversarial_user_rules.rstrip(), updated)
        self.assertEqual(updated.count(TAG_START), 1)

    def test_rule_fencing_unicode_multilingual_and_emojis(self) -> None:
        unicode_rules = (
            "# 🌐 আন্তর্জাতিক নীতিমালা\n\n"
            "• বাংলা: বাংলা ভাষার নিয়ম কানুন অক্ষুণ্ণ রাখতে হবে।\n"
            "• 日本語: 常にテストを実行してください。\n"
            "• Emojis: 🚀 🧪 🛡️ 🐾 🐱\n"
        )
        agents_file = self.ws / "AGENTS.md"
        agents_file.write_text(
            unicode_rules + f"\n\n{LEGACY_TAG_START}\nold\n{LEGACY_TAG_END}\n",
            encoding="utf-8",
        )

        res = harmonize_workspace(self.ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        updated = agents_file.read_text(encoding="utf-8")
        self.assertIn(unicode_rules.rstrip(), updated)

    def test_rule_fencing_malformed_empty_and_mismatched(self) -> None:
        # 1. Empty fences
        empty_fence = f"{LEGACY_TAG_START}\n{LEGACY_TAG_END}"
        agents_file = self.ws / "AGENTS.md"
        agents_file.write_text(empty_fence, encoding="utf-8")
        res1 = harmonize_workspace(self.ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res1.success)
        self.assertEqual(agents_file.read_text(encoding="utf-8").count(TAG_START), 1)

        # 2. Mismatched start and end tags
        mismatched = f"{LEGACY_TAG_START}\nSome content\n{TAG_END}"
        agents_file.write_text(mismatched, encoding="utf-8")
        res2 = harmonize_workspace(self.ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res2.success)
        updated = agents_file.read_text(encoding="utf-8")
        self.assertEqual(updated.count(TAG_START), 1)
        self.assertNotIn(LEGACY_TAG_START, updated)

        # 3. Unclosed tag
        unclosed = f"{LEGACY_TAG_START}\nUnclosed block\n"
        agents_file.write_text(unclosed, encoding="utf-8")
        res3 = harmonize_workspace(self.ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res3.success)
        updated3 = agents_file.read_text(encoding="utf-8")
        self.assertIn(TAG_START, updated3)
        self.assertIn(TAG_END, updated3)

    def test_rule_fencing_crlf_windows_line_endings(self) -> None:
        crlf_content = f"# Windows Rules\r\n\r\n{LEGACY_TAG_START}\r\n# Legacy\r\n{LEGACY_TAG_END}\r\n\r\n# Tail\r\n"
        agents_file = self.ws / "AGENTS.md"
        agents_file.write_bytes(crlf_content.encode("utf-8"))

        res = harmonize_workspace(self.ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        updated = agents_file.read_text(encoding="utf-8")
        self.assertNotIn(LEGACY_TAG_START, updated)
        self.assertIn(TAG_START, updated)
        self.assertIn(TAG_END, updated)
        self.assertIn("# Windows Rules", updated)

    def test_untagged_custom_rules_injection(self) -> None:
        agents_md = self.ws / "AGENTS.md"
        agents_md.write_text(
            "# Purrmission Ground Rules\n- Wait 10 mins before merge\n", encoding="utf-8"
        )

        res = harmonize_workspace(self.ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        self.assertEqual(res.rules_action, "inserted_tagged_block")

        updated = agents_md.read_text(encoding="utf-8")
        self.assertTrue(
            updated.startswith("# Purrmission Ground Rules\n- Wait 10 mins before merge\n")
        )
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", updated)

    def test_create_agents_md_when_missing(self) -> None:
        res = harmonize_workspace(self.ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        self.assertEqual(res.rules_action, "created_rules_file")
        self.assertTrue((self.ws / "AGENTS.md").is_file())
        content = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", content)

    def test_idempotent_harmonization(self) -> None:
        # First pass
        res1 = harmonize_workspace(self.ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res1.success)
        self.assertTrue(res1.modified)

        # Second pass
        res2 = harmonize_workspace(self.ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res2.success)
        self.assertFalse(res2.modified)
        self.assertEqual(res2.rules_action, "already_up_to_date")

    def test_nonexistent_workspace(self) -> None:
        non_existent = self.ws / "does_not_exist"
        res = harmonize_workspace(non_existent)
        self.assertFalse(res.success)
        self.assertIn("does not exist", res.message)

    # --- Dry-Run Isolation Tests ---

    def test_dry_run_zero_filesystem_mutations(self) -> None:
        agent_dir = self.ws / ".agent"
        (agent_dir / "agents").mkdir(parents=True)
        (agent_dir / "agents" / "helper.md").write_text("# Helper Agent", encoding="utf-8")

        (agent_dir / "workflows").mkdir(parents=True)
        (agent_dir / "workflows" / "deploy.md").write_text(
            "# Deploy Workflow\nRuns deploy.", encoding="utf-8"
        )

        (agent_dir / "rules").mkdir(parents=True)
        (agent_dir / "rules" / "rule.md").write_text("# Rule", encoding="utf-8")

        agents_md = self.ws / "AGENTS.md"
        agents_md.write_text(
            "# Custom Rules\n- Be fast\n\n<!-- Added by PSL-HARNESS -->\nLegacy\n<!-- End PSL-HARNESS -->\n",
            encoding="utf-8",
        )
        original_md_content = agents_md.read_text(encoding="utf-8")

        res = harmonize_workspace(self.ws, dry_run=True, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        self.assertTrue(res.dry_run)
        self.assertTrue(res.modified)
        self.assertTrue(res.legacy_agent_dir_found)
        self.assertIn("helper.md", res.legacy_agents_migrated)
        self.assertIn("deploy", res.legacy_workflows_migrated)
        self.assertIn("rule.md", res.legacy_rules_migrated)
        self.assertEqual(res.rules_action, "migrated_tagged_block")

        # Invariant check: .agents/ directory MUST NOT exist
        self.assertFalse((self.ws / ".agents").exists())
        # Invariant check: AGENTS.md content MUST NOT have changed
        self.assertEqual(agents_md.read_text(encoding="utf-8"), original_md_content)

    def test_dry_run_sha256_tree_stability_complex_fixture(self) -> None:
        agent_dir = self.ws / ".agent"
        (agent_dir / "agents").mkdir(parents=True)
        (agent_dir / "workflows").mkdir(parents=True)
        (agent_dir / "rules").mkdir(parents=True)
        (self.ws / "workflows").mkdir(parents=True)

        (agent_dir / "agents" / "agent.md").write_text("# Agent", encoding="utf-8")
        (agent_dir / "workflows" / "flow.md").write_text("# Flow\nDoes stuff.", encoding="utf-8")
        (agent_dir / "rules" / "rule.md").write_text("# Rule", encoding="utf-8")
        (self.ws / "workflows" / "root.md").write_text("# Root", encoding="utf-8")
        (self.ws / "package.json").write_text(json.dumps({"scripts": {"test": "vitest"}}), encoding="utf-8")
        (self.ws / "AGENTS.md").write_text(f"{LEGACY_TAG_START}\nold\n{LEGACY_TAG_END}", encoding="utf-8")

        initial_hashes = hash_directory_tree(self.ws)
        self.assertGreater(len(initial_hashes), 0)

        res = harmonize_workspace(self.ws, dry_run=True, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        self.assertTrue(res.dry_run)
        self.assertTrue(res.modified)
        self.assertFalse((self.ws / ".agents").exists())

        post_hashes = hash_directory_tree(self.ws)
        self.assertEqual(initial_hashes, post_hashes)

    def test_dry_run_read_only_agents_md(self) -> None:
        agents_file = self.ws / "AGENTS.md"
        agents_file.write_text(f"{LEGACY_TAG_START}\nlegacy\n{LEGACY_TAG_END}\n", encoding="utf-8")
        os.chmod(agents_file, stat.S_IREAD)

        try:
            res = harmonize_workspace(self.ws, dry_run=True, source_dir=REPO_ROOT)
            self.assertTrue(res.success)
            self.assertTrue(res.dry_run)
            self.assertTrue(res.modified)
        finally:
            os.chmod(agents_file, stat.S_IREAD | stat.S_IWRITE)

    # --- Command Dictionary Extraction in Harmonizer ---

    def test_harmonize_command_dictionary_node_python_makefile(self) -> None:
        (self.ws / "package.json").write_text(
            json.dumps({"scripts": {"test": "npm test", "build": "npm run build"}}),
            encoding="utf-8",
        )
        res = harmonize_workspace(self.ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        self.assertIn("test", res.command_dictionary)
        self.assertIn("npm test", res.command_dictionary["test"])

        agents_content = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("# 🧪 Project Verification & Native Toolchain", agents_content)
        self.assertIn("npm test", agents_content)

    def test_harmonize_corrupted_manifests_graceful(self) -> None:
        (self.ws / "package.json").write_text('{"scripts": { "test": "broken', encoding="utf-8")
        (self.ws / "pyproject.toml").write_text('[project\nname = "unclosed\n', encoding="utf-8")
        (self.ws / "Makefile").write_bytes(b"\x00\xff\xfeBINARY_GARBAGE\x00")

        res = harmonize_workspace(self.ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        self.assertIsInstance(res.command_dictionary, dict)
        self.assertTrue((self.ws / "AGENTS.md").is_file())


class TestHarmonizeCLI(unittest.TestCase):
    """Hermetic CLI tests for agyis harmonize and psl harmonize."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_cli_harmonize_dry_run_json(self) -> None:
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
            code = main(["harmonize", str(self.ws), "--dry-run", "--json"], prog="agyis")

        self.assertEqual(code, 0)
        out = json.loads(stdout_buf.getvalue())
        self.assertTrue(out["success"])
        self.assertTrue(out["dry_run"])
        self.assertEqual(out["rules_action"], "created_rules_file")

    def test_cli_psl_harmonize_deprecation_warning(self) -> None:
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
            code = main(["harmonize", str(self.ws), "--json"], prog="psl")

        self.assertEqual(code, 0)
        self.assertIn("DeprecationWarning: 'psl' is deprecated", stderr_buf.getvalue())
        out = json.loads(stdout_buf.getvalue())
        self.assertTrue(out["success"])
        self.assertFalse(out["dry_run"])

    def test_cli_harmonize_human_output(self) -> None:
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
            code = main(["harmonize", str(self.ws), "--dry-run"], prog="agyis")

        self.assertEqual(code, 0)
        out = stdout_buf.getvalue()
        self.assertIn("✔ [DRY-RUN]", out)
        self.assertIn("Disk status: Zero modifications made", out)

    def test_cli_harmonize_json_schema_completeness(self) -> None:
        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            code = main(["harmonize", str(self.ws), "--json"], prog="agyis")

        self.assertEqual(code, 0)
        data = json.loads(stdout_buf.getvalue())
        expected_keys = {
            "success",
            "workspace_dir",
            "dry_run",
            "legacy_agent_dir_found",
            "legacy_workflows_migrated",
            "legacy_agents_migrated",
            "legacy_rules_migrated",
            "rules_action",
            "command_dictionary",
            "modified",
            "message",
        }
        self.assertTrue(expected_keys.issubset(set(data.keys())))
        self.assertIsInstance(data["success"], bool)
        self.assertIsInstance(data["dry_run"], bool)
        self.assertIsInstance(data["modified"], bool)
        self.assertIsInstance(data["command_dictionary"], dict)

    def test_cli_psl_harmonize_json_stderr_isolation(self) -> None:
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
            code = main(["harmonize", str(self.ws), "--dry-run", "--json"], prog="psl")

        self.assertEqual(code, 0)
        # Verify stderr has the deprecation notice
        self.assertIn("DeprecationWarning: 'psl' is deprecated", stderr_buf.getvalue())
        # Verify stdout is 100% pure parseable JSON without deprecation text
        stdout_str = stdout_buf.getvalue().strip()
        data = json.loads(stdout_str)
        self.assertTrue(data["success"])
        self.assertTrue(data["dry_run"])
        self.assertNotIn("DeprecationWarning", stdout_str)

    def test_cli_harmonize_failure_nonexistent_workspace(self) -> None:
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        non_existent = self.ws / "definitely_does_not_exist"
        with patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
            code = main(["harmonize", str(non_existent), "--json"], prog="agyis")

        self.assertEqual(code, 1)
        data = json.loads(stdout_buf.getvalue())
        self.assertFalse(data["success"])
        self.assertIn("does not exist", data["message"])


if __name__ == "__main__":
    unittest.main()
