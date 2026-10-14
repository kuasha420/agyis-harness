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
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from harness.cli import main
from harness.delivery.constants import REPO_ROOT
from harness.delivery.harmonize import (
    HarmonizeResult,
    harmonize_workspace,
    sanitize_workspace_links,
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
            "pruned_legacy",
            "backup_archive",
            "backup_manifest",
            "untracked_debris_cleaned",
            "skills_provisioned",
        }
        self.assertTrue(expected_keys.issubset(set(data.keys())))
        self.assertIsInstance(data["success"], bool)
        self.assertIsInstance(data["dry_run"], bool)
        self.assertIsInstance(data["modified"], bool)
        self.assertIsInstance(data["command_dictionary"], dict)
        self.assertIsInstance(data["pruned_legacy"], bool)
        self.assertIsInstance(data["untracked_debris_cleaned"], list)

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

    def test_cli_harmonize_prune_flags(self) -> None:
        """CLI --prune-legacy and alias --clean-agent-dir prune legacy .agent/ cleanly."""
        # 1. Test --prune-legacy
        ws1 = self.ws / "cli_prune_1"
        ws1.mkdir()
        (ws1 / ".agent" / "rules").mkdir(parents=True)
        (ws1 / ".agent" / "rules" / "rule1.md").write_text("# Rule 1\n", encoding="utf-8")

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            code = main(["harmonize", str(ws1), "--prune-legacy", "--json"], prog="agyis")
        self.assertEqual(code, 0)
        data1 = json.loads(stdout_buf.getvalue())
        self.assertTrue(data1["success"])
        self.assertTrue(data1["pruned_legacy"])
        self.assertFalse((ws1 / ".agent").exists())
        self.assertTrue((ws1 / ".agents" / "rules" / "rule1.md").is_file())

        # 2. Test alias --clean-agent-dir
        ws2 = self.ws / "cli_prune_2"
        ws2.mkdir()
        (ws2 / ".agent" / "rules").mkdir(parents=True)
        (ws2 / ".agent" / "rules" / "rule2.md").write_text("# Rule 2\n", encoding="utf-8")

        stdout_buf2 = io.StringIO()
        with patch("sys.stdout", stdout_buf2):
            code = main(["harmonize", str(ws2), "--clean-agent-dir", "--json"], prog="agyis")
        self.assertEqual(code, 0)
        data2 = json.loads(stdout_buf2.getvalue())
        self.assertTrue(data2["success"])
        self.assertTrue(data2["pruned_legacy"])
        self.assertFalse((ws2 / ".agent").exists())
        self.assertTrue((ws2 / ".agents" / "rules" / "rule2.md").is_file())

    def test_cli_harmonize_no_backup_flag(self) -> None:
        """CLI --prune-legacy with --no-backup prunes legacy directory with zero backup archive."""
        ws_nobackup = self.ws / "cli_nobackup"
        ws_nobackup.mkdir()
        (ws_nobackup / ".agent" / "rules").mkdir(parents=True)
        (ws_nobackup / ".agent" / "rules" / "rule.md").write_text("# Rule\n", encoding="utf-8")

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            code = main(["harmonize", str(ws_nobackup), "--prune-legacy", "--no-backup", "--json"], prog="agyis")
        self.assertEqual(code, 0)
        data = json.loads(stdout_buf.getvalue())
        self.assertTrue(data["success"])
        self.assertTrue(data["pruned_legacy"])
        self.assertIsNone(data["backup_archive"])
        self.assertFalse((ws_nobackup / ".agent").exists())
        self.assertFalse((ws_nobackup / ".agents" / "archive").exists())

    def test_cli_harmonize_custom_archive_dir(self) -> None:
        """CLI --backup-dir / --archive-dir saves archive to custom location."""
        ws_custom = self.ws / "cli_custom_arch"
        ws_custom.mkdir()
        (ws_custom / ".agent" / "rules").mkdir(parents=True)
        (ws_custom / ".agent" / "rules" / "r.md").write_text("# R\n", encoding="utf-8")
        custom_arch = self.ws / "my_custom_archives"

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            code = main(["harmonize", str(ws_custom), "--prune-legacy", "--backup-dir", str(custom_arch), "--json"], prog="agyis")
        self.assertEqual(code, 0)
        data = json.loads(stdout_buf.getvalue())
        self.assertTrue(data["success"])
        self.assertTrue(data["pruned_legacy"])
        self.assertTrue(custom_arch.is_dir())
        self.assertTrue(Path(data["backup_archive"]).is_file())
        self.assertEqual(Path(data["backup_archive"]).parent, custom_arch.resolve())


class TestHarmonizeDeprecationLifecycle(unittest.TestCase):
    """Hermetic unit tests for the 4-Phase Atomic Legacy Deprecation Lifecycle."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _init_git_repo(self, path: Path) -> None:
        subprocess.run(["git", "init"], cwd=path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        subprocess.run(["git", "config", "user.email", "agent@test.local"], cwd=path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    def test_atomic_pruning_with_tarball_backup(self) -> None:
        """Phase 1-4: verifies files migrate, archive tarball is created with digests, and .agent/ is pruned."""
        agent_dir = self.ws / ".agent"
        (agent_dir / "agents").mkdir(parents=True)
        (agent_dir / "agents" / "architect.md").write_text("# Architect\nRole instructions.", encoding="utf-8")

        (agent_dir / "workflows").mkdir(parents=True)
        (agent_dir / "workflows" / "deploy.md").write_text("# Deploy Runbook\nDeploy steps.", encoding="utf-8")

        (agent_dir / "rules").mkdir(parents=True)
        (agent_dir / "rules" / "standards.md").write_text("# Standards\nCoding rules.", encoding="utf-8")

        (agent_dir / "extra").mkdir(parents=True)
        (agent_dir / "extra" / "config.json").write_text('{"custom": true}', encoding="utf-8")

        res = harmonize_workspace(self.ws, prune_legacy=True, backup=True)
        self.assertTrue(res.success)
        self.assertTrue(res.pruned_legacy)
        self.assertFalse(agent_dir.exists())

        # Migrated destinations exist
        self.assertTrue((self.ws / ".agents" / "agents" / "architect.md").is_file())
        self.assertTrue((self.ws / ".agents" / "skills" / "deploy" / "SKILL.md").is_file())
        self.assertTrue((self.ws / ".agents" / "rules" / "standards.md").is_file())

        # Archive tarball and manifest exist
        self.assertIsNotNone(res.backup_archive)
        self.assertTrue(res.backup_archive.is_file())
        self.assertTrue((self.ws / ".agents" / "archive").is_dir())
        self.assertIsNotNone(res.backup_manifest)
        self.assertGreaterEqual(res.backup_manifest["file_count"], 4)

        # Inspect tarball contents
        with tarfile.open(res.backup_archive, "r:gz") as tar:
            names = tar.getnames()
            self.assertIn(".agent/agents/architect.md", names)
            self.assertIn(".agent/workflows/deploy.md", names)
            self.assertIn(".agent/rules/standards.md", names)
            self.assertIn(".agent/extra/config.json", names)

            # Verify content integrity in archive
            archived_cfg = tar.extractfile(".agent/extra/config.json")
            self.assertIsNotNone(archived_cfg)
            self.assertEqual(archived_cfg.read().decode("utf-8"), '{"custom": true}')

    def test_atomic_pruning_no_backup(self) -> None:
        """Phase 4 without Phase 3: prunes legacy directory with zero archive folder created."""
        (self.ws / ".agent" / "rules").mkdir(parents=True)
        (self.ws / ".agent" / "rules" / "rule.md").write_text("# Rule\n", encoding="utf-8")

        res = harmonize_workspace(self.ws, prune_legacy=True, backup=False)
        self.assertTrue(res.success)
        self.assertTrue(res.pruned_legacy)
        self.assertFalse((self.ws / ".agent").exists())
        self.assertIsNone(res.backup_archive)
        self.assertIsNone(res.backup_manifest)
        self.assertFalse((self.ws / ".agents" / "archive").exists())

    def test_untracked_debris_cleanup_in_git_repo(self) -> None:
        """Prunes git-tracked files via git rm and sweeps untracked debris via shutil.rmtree."""
        self._init_git_repo(self.ws)
        agent_dir = self.ws / ".agent"
        (agent_dir / "rules").mkdir(parents=True)
        (agent_dir / "rules" / "tracked_rule.md").write_text("# Tracked\n", encoding="utf-8")

        subprocess.run(["git", "add", ".agent"], cwd=self.ws, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        subprocess.run(["git", "commit", "-m", "add tracked legacy rule"], cwd=self.ws, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        # Create untracked debris
        (agent_dir / "untracked_note.txt").write_text("local note\n", encoding="utf-8")
        (agent_dir / "cache").mkdir(parents=True)
        (agent_dir / "cache" / "debris.dat").write_text("cache-data\n", encoding="utf-8")

        res = harmonize_workspace(self.ws, prune_legacy=True, backup=True)
        self.assertTrue(res.success)
        self.assertTrue(res.pruned_legacy)
        self.assertFalse(agent_dir.exists())
        self.assertIn("untracked_note.txt", res.untracked_debris_cleaned)
        self.assertIn("cache/debris.dat", res.untracked_debris_cleaned)

        # Verify git status reflects deletion of tracked files
        proc = subprocess.run(["git", "status", "--porcelain"], cwd=self.ws, stdout=subprocess.PIPE, text=True, check=True)
        self.assertIn("D  .agent/rules/tracked_rule.md", proc.stdout)

    def test_dry_run_pruning_preserves_disk(self) -> None:
        """Dry-run preview computes planned actions with zero filesystem mutation."""
        agent_dir = self.ws / ".agent"
        (agent_dir / "rules").mkdir(parents=True)
        (agent_dir / "rules" / "r1.md").write_text("# R1\n", encoding="utf-8")

        res = harmonize_workspace(self.ws, dry_run=True, prune_legacy=True, backup=True)
        self.assertTrue(res.success)
        self.assertTrue(res.dry_run)
        self.assertTrue(res.pruned_legacy)
        self.assertTrue(agent_dir.exists())
        self.assertTrue((agent_dir / "rules" / "r1.md").is_file())
        self.assertFalse((self.ws / ".agents" / "archive").exists())
        self.assertIsNotNone(res.backup_archive)
        self.assertIsNotNone(res.backup_manifest)

    def test_dry_run_git_repo_preserves_git_exclude(self) -> None:
        """In a Git repo, harmonize with dry_run=True leaves .git/info/exclude untouched."""
        self._init_git_repo(self.ws)
        agent_dir = self.ws / ".agent"
        (agent_dir / "rules").mkdir(parents=True)
        (agent_dir / "rules" / "r.md").write_text("# Rule\n", encoding="utf-8")

        exclude_file = self.ws / ".git" / "info" / "exclude"
        initial_exclude = exclude_file.read_bytes() if exclude_file.exists() else None

        res = harmonize_workspace(self.ws, dry_run=True, prune_legacy=True, backup=True)
        self.assertTrue(res.success)
        self.assertTrue(res.dry_run)
        self.assertTrue(res.pruned_legacy)

        after_exclude = exclude_file.read_bytes() if exclude_file.exists() else None
        self.assertEqual(initial_exclude, after_exclude)
        if exclude_file.exists():
            self.assertNotIn(b"Agyis Harness Ignored", exclude_file.read_bytes())

    def test_zero_byte_legacy_markdown_rule_migrates_cleanly(self) -> None:
        """A 0-byte legacy markdown rule in .agent/rules/ migrates cleanly without false integrity failure."""
        agent_dir = self.ws / ".agent"
        (agent_dir / "rules").mkdir(parents=True)
        empty_rule = agent_dir / "rules" / "empty.md"
        empty_rule.write_text("", encoding="utf-8")

        res = harmonize_workspace(self.ws, prune_legacy=True, backup=True)
        self.assertTrue(res.success)
        dst_rule = self.ws / ".agents" / "rules" / "empty.md"
        self.assertTrue(dst_rule.is_file())
        self.assertEqual(dst_rule.stat().st_size, 0)

    def test_custom_archive_dir(self) -> None:
        """Specifying archive_dir places tarball in requested directory."""
        (self.ws / ".agent" / "rules").mkdir(parents=True)
        (self.ws / ".agent" / "rules" / "r.md").write_text("# R\n", encoding="utf-8")
        custom_archive = self.ws / "my_custom_vault"

        res = harmonize_workspace(self.ws, prune_legacy=True, backup=True, archive_dir=custom_archive)
        self.assertTrue(res.success)
        self.assertTrue(res.pruned_legacy)
        self.assertFalse((self.ws / ".agent").exists())
        self.assertTrue(custom_archive.is_dir())
        self.assertEqual(res.backup_archive.parent, custom_archive.resolve())
        self.assertTrue(res.backup_archive.is_file())
        self.assertFalse((self.ws / ".agents" / "archive").exists())

    def test_user_rules_markdown_link_rewriting(self) -> None:
        """Rewrites internal .agent/rules/ references to .agents/rules/ across user markdown files."""
        (self.ws / ".agent" / "rules").mkdir(parents=True)
        (self.ws / ".agent" / "rules" / "coding.md").write_text(
            "# Coding\nReference to .agent/rules/security.md for authentication standards.\n",
            encoding="utf-8",
        )
        (self.ws / ".agent" / "rules" / "security.md").write_text("# Security\nAuth tokens.\n", encoding="utf-8")

        (self.ws / "AGENTS.md").write_text(
            "# Root Invariants\n- See [.agent/rules/coding.md](.agent/rules/coding.md)\n- See `.agent/rules/security.md`\n",
            encoding="utf-8",
        )

        res = harmonize_workspace(self.ws, prune_legacy=True, backup=True)
        self.assertTrue(res.success)

        # Verify AGENTS.md links rewritten
        root_rules = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(".agents/rules/coding.md", root_rules)
        self.assertIn(".agents/rules/security.md", root_rules)
        self.assertNotIn(".agent/rules/coding.md", root_rules)

        # Verify migrated rule links rewritten
        migrated_coding = (self.ws / ".agents" / "rules" / "coding.md").read_text(encoding="utf-8")
        self.assertIn(".agents/rules/security.md", migrated_coding)
        self.assertNotIn(".agent/rules/security.md", migrated_coding)

    def test_git_exclusion_of_archive_and_patch(self) -> None:
        """Asserts configure_git_exclude ensures .agents/archive/ and *.patch are excluded."""
        self._init_git_repo(self.ws)
        (self.ws / ".agent" / "rules").mkdir(parents=True)
        (self.ws / ".agent" / "rules" / "r.md").write_text("# R\n", encoding="utf-8")

        res = harmonize_workspace(self.ws, prune_legacy=True, backup=True)
        self.assertTrue(res.success)

        exclude_file = self.ws / ".git" / "info" / "exclude"
        self.assertTrue(exclude_file.is_file())
        exclude_content = exclude_file.read_text(encoding="utf-8")
        self.assertIn(".agents/archive/", exclude_content)
        self.assertIn("*.patch", exclude_content)

    def test_harmonize_stack_and_skills_provisioning(self) -> None:
        """Harmonization provisions stack skills into .agents/skills/ when --stack/--skills is provided."""
        (self.ws / ".agent" / "rules").mkdir(parents=True)
        (self.ws / ".agent" / "rules" / "r.md").write_text("# R\n", encoding="utf-8")

        res = harmonize_workspace(self.ws, prune_legacy=True, skills=["psl-stack-shell"])
        self.assertTrue(res.success)
        self.assertTrue((self.ws / ".agents" / "skills" / "psl-stack-shell" / "SKILL.md").is_file())
        self.assertIn("psl-stack-shell", res.skills_provisioned)


class TestWorkspacePythonCommandExtraction(unittest.TestCase):
    """Hermetic tests validating Python test runner discovery (dead code removal in workspace.py)."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_python_unittest_discovery_when_pytest_absent(self) -> None:
        """When pyproject.toml does not configure pytest and tests/ exists, unittest runner is extracted."""
        (self.ws / "pyproject.toml").write_text(
            "[project]\nname = 'pure-unittest-app'\nversion = '0.1.0'\n",
            encoding="utf-8",
        )
        (self.ws / "tests").mkdir(parents=True)
        (self.ws / "tests" / "test_sample.py").write_text("import unittest\n", encoding="utf-8")

        cmds = extract_command_dictionary(self.ws)
        self.assertEqual(cmds.get("test"), "python3 -m unittest discover -s tests -v")

    def test_python_pytest_discovery_when_pytest_configured(self) -> None:
        """When pyproject.toml explicitly configures pytest, pytest runner is extracted."""
        (self.ws / "pyproject.toml").write_text(
            "[project]\nname = 'pytest-app'\n[tool.pytest.ini_options]\naddopts = '-v'\n",
            encoding="utf-8",
        )
        (self.ws / "tests").mkdir(parents=True)
        (self.ws / "tests" / "test_sample.py").write_text("import pytest\n", encoding="utf-8")

        cmds = extract_command_dictionary(self.ws)
        self.assertEqual(cmds.get("test"), "pytest")


class TestWorkspaceLinkSanitizer(unittest.TestCase):
    """Hermetic unit tests for recursive link sanitization (.agent/ -> .agents/)."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name) / "workspace"
        self.ws.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_sanitize_workspace_links_basic(self) -> None:
        """sanitize_workspace_links rewrites legacy .agent/ references in .agents/ and AGENTS.md."""
        agents_skill_dir = self.ws / ".agents" / "skills" / "demo"
        agents_skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = agents_skill_dir / "SKILL.md"
        skill_file.write_text(
            "---\nname: demo\n---\nSee [.agent/rules/r.md](.agent/rules/r.md) and `cat .agent/workflows/w.md`.\n",
            encoding="utf-8",
        )

        root_agents = self.ws / "AGENTS.md"
        root_agents.write_text(
            "# Rules\nRefer to `.agent/skills/demo/SKILL.md`.\n",
            encoding="utf-8",
        )

        sanitized = sanitize_workspace_links(self.ws)
        self.assertEqual(len(sanitized), 2)

        # Check content
        skill_text = skill_file.read_text(encoding="utf-8")
        self.assertNotIn(".agent/", skill_text)
        self.assertIn(".agents/rules/r.md", skill_text)
        self.assertIn(".agents/workflows/w.md", skill_text)

        root_text = root_agents.read_text(encoding="utf-8")
        self.assertNotIn(".agent/", root_text)
        self.assertIn(".agents/skills/demo/SKILL.md", root_text)

        # Idempotent re-run
        sanitized_again = sanitize_workspace_links(self.ws)
        self.assertEqual(len(sanitized_again), 0)

    def test_harmonize_workspace_integration_sanitizes_links(self) -> None:
        """harmonize_workspace automatically applies sanitize_workspace_links."""
        # Existing skill in .agents/ that has un-sanitized .agent/ reference
        custom_skill = self.ws / ".agents" / "skills" / "custom"
        custom_skill.mkdir(parents=True, exist_ok=True)
        (custom_skill / "SKILL.md").write_text(
            "---\nname: custom\n---\nSee .agent/rules/custom.md\n",
            encoding="utf-8",
        )

        legacy_wf = self.ws / ".agent" / "workflows"
        legacy_wf.mkdir(parents=True, exist_ok=True)
        (legacy_wf / "deploy.md").write_text(
            "# Deploy\nRun deployment. See .agent/rules/r.md\n",
            encoding="utf-8",
        )

        res = harmonize_workspace(self.ws, prune_legacy=True)
        self.assertTrue(res.success)
        self.assertTrue(len(res.sanitized_files) > 0)
        self.assertIn(".agents/skills/custom/SKILL.md", res.sanitized_files)

        custom_text = (custom_skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn(".agent/rules/custom.md", custom_text)
        self.assertIn(".agents/rules/custom.md", custom_text)

        migrated_skill = self.ws / ".agents" / "skills" / "deploy" / "SKILL.md"
        self.assertTrue(migrated_skill.is_file())
        content = migrated_skill.read_text(encoding="utf-8")
        self.assertNotIn(".agent/rules/r.md", content)
        self.assertIn(".agents/rules/r.md", content)


if __name__ == "__main__":
    unittest.main()
