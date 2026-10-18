#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic test suite for conventional release notes generator (Milestone M1).
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from harness.cli import main
from harness.delivery.release_notes import (
    CATEGORY_DOCS,
    CATEGORY_FEATURES,
    CATEGORY_FIXES,
    CATEGORY_MAINTENANCE,
    DEFAULT_REPO_URL,
    categorize_commits,
    extract_issue_references,
    find_previous_tag,
    format_markdown,
    generate_release_notes,
    get_repo_remote_url,
    parse_commit_record,
    parse_commits,
    sync_github_release,
)


class TestCommitParsing(unittest.TestCase):
    """Tests for raw git log parsing and conventional commit attribute extraction."""

    def test_parse_conventional_feat_with_scope_and_issue(self):
        log_sample = "cced547\x1ffeat(cli): onboard engine completion (#58)\x1fCloses #58\x1e"
        commits = parse_commits(log_sample)
        self.assertEqual(len(commits), 1)
        c = commits[0]
        self.assertEqual(c["hash"], "cced547")
        self.assertEqual(c["type"], "feat")
        self.assertEqual(c["scope"], "cli")
        self.assertEqual(c["description"], "onboard engine completion (#58)")
        self.assertEqual(c["issues"], ["58"])
        self.assertFalse(c["breaking"])
        self.assertFalse(c["is_merge"])

    def test_parse_fix_no_scope(self):
        log_sample = "20a4e95\x1ffix: fix jitter benchmark\x1f\x1e"
        commits = parse_commits(log_sample)
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0]["type"], "fix")
        self.assertIsNone(commits[0]["scope"])
        self.assertEqual(commits[0]["description"], "fix jitter benchmark")

    def test_parse_breaking_change_exclamation(self):
        log_sample = "abc1234\x1ffeat(api)!: drop deprecated method\x1f\x1e"
        commits = parse_commits(log_sample)
        self.assertEqual(len(commits), 1)
        self.assertTrue(commits[0]["breaking"])

    def test_parse_breaking_change_in_body(self):
        log_sample = (
            "abc1234\x1ffeat(api): update schema\x1f"
            "BREAKING CHANGE: old schema invalid\x1e"
        )
        commits = parse_commits(log_sample)
        self.assertEqual(len(commits), 1)
        self.assertTrue(commits[0]["breaking"])

    def test_parse_merge_commits_flagged(self):
        log_sample = "4ea03f5\x1fMerge pull request #48 from kuasha420/feat/rea\x1f\x1e"
        commits = parse_commits(log_sample)
        self.assertEqual(len(commits), 1)
        self.assertTrue(commits[0]["is_merge"])

    def test_parse_full_7_field_record(self):
        record = (
            "cced547df3f43ecf964c9ed3b19bb12689514528\x1f"
            "cced547\x1f"
            "Arafat Zahan\x1f"
            "kuasha420@gmail.com\x1f"
            "2026-10-18T09:58:31+06:00\x1f"
            "feat(cli): unified agyis onboard CLI engine completion (#58)\x1f"
            "- Add CLI flags --allow-dirty\n"
            "- Implement dirty working tree safety gate\n\n"
            "Closes #58\x1e"
        )
        commits = parse_commits(record)
        self.assertEqual(len(commits), 1)
        c = commits[0]
        self.assertEqual(c["hash"], "cced547df3f43ecf964c9ed3b19bb12689514528")
        self.assertEqual(c["short_hash"], "cced547")
        self.assertEqual(c["author_name"], "Arafat Zahan")
        self.assertEqual(c["author_email"], "kuasha420@gmail.com")
        self.assertEqual(c["type"], "feat")
        self.assertEqual(c["scope"], "cli")
        self.assertEqual(len(c["sub_bullets"]), 2)
        self.assertEqual(c["sub_bullets"][0], "Add CLI flags --allow-dirty")
        self.assertIn("58", c["issues"])

    def test_parse_empty_input(self):
        self.assertEqual(parse_commits(""), [])
        self.assertEqual(parse_commits("   \n  "), [])
        self.assertIsNone(parse_commit_record("   "))


class TestIssueExtraction(unittest.TestCase):
    """Tests for regex-based issue and pull request extraction."""

    def test_extract_various_formats(self):
        sample = (
            "feat(cli): onboard engine (#58)\n"
            "This closes #52 and fixes #53. PR #40 relates to this.\n"
            "Also see Issues #44, #45."
        )
        issues = extract_issue_references(sample)
        self.assertEqual(issues, ["58", "52", "53", "40", "44", "45"])

    def test_extract_no_false_positives(self):
        sample = "fix: update color to #ffffff and C# macro #define TEST"
        issues = extract_issue_references(sample)
        self.assertEqual(issues, [])


class TestCategorization(unittest.TestCase):
    """Tests for mapping commit types to canonical sections."""

    def test_categorization_buckets(self):
        commits = [
            {"type": "feat", "subject": "feat: a", "is_merge": False},
            {"type": "fix", "subject": "fix: b", "is_merge": False},
            {"type": "perf", "subject": "perf: c", "is_merge": False},
            {"type": "docs", "subject": "docs: d", "is_merge": False},
            {"type": "chore", "subject": "chore: e", "is_merge": False},
            {"type": "refactor", "subject": "refactor: f", "is_merge": False},
            {"type": "unknown", "subject": "random commit", "is_merge": False},
            {"type": "feat", "subject": "Merge pull request #1", "is_merge": True},
        ]
        cats = categorize_commits(commits)
        self.assertEqual(len(cats[CATEGORY_FEATURES]), 1)
        self.assertEqual(len(cats[CATEGORY_FIXES]), 2)  # fix, perf
        self.assertEqual(len(cats[CATEGORY_DOCS]), 1)
        self.assertEqual(len(cats[CATEGORY_MAINTENANCE]), 3)  # chore, refactor, unknown


class TestMarkdownFormatting(unittest.TestCase):
    """Tests for Markdown changelog rendering and URL formatting."""

    def test_formatting_with_comparison(self):
        cats = {
            CATEGORY_FEATURES: [
                {
                    "subject": "feat(cli): new flag (#58)",
                    "sub_bullets": ["Add flag implementation"],
                }
            ],
            CATEGORY_FIXES: [{"subject": "fix(core): crash fix", "sub_bullets": []}],
            CATEGORY_DOCS: [],
            CATEGORY_MAINTENANCE: [],
        }
        md = format_markdown(cats, base_tag="v1.0.0-rc4", target_tag="v1.0.0-rc5")
        self.assertIn("## What's Changed", md)
        self.assertIn("### Features & Architecture", md)
        self.assertIn("- feat(cli): new flag (#58)", md)
        self.assertIn("  - Add flag implementation", md)
        self.assertIn("### Bug Fixes & Hardening", md)
        self.assertNotIn("### Documentation & Usability", md)
        self.assertNotIn("### Maintenance & Release", md)
        self.assertIn(
            "**Full Changelog**: https://github.com/kuasha420/agyis-harness/compare/v1.0.0-rc4...v1.0.0-rc5",
            md,
        )

    def test_formatting_without_base_tag(self):
        cats = {
            CATEGORY_FEATURES: [{"subject": "feat: initial commit"}],
            CATEGORY_FIXES: [],
            CATEGORY_DOCS: [],
            CATEGORY_MAINTENANCE: [],
        }
        md = format_markdown(cats, base_tag=None, target_tag="v1.0.0")
        self.assertIn("**Full Changelog**: https://github.com/kuasha420/agyis-harness/commits/v1.0.0", md)

    def test_formatting_empty_categories(self):
        cats = {
            CATEGORY_FEATURES: [],
            CATEGORY_FIXES: [],
            CATEGORY_DOCS: [],
            CATEGORY_MAINTENANCE: [],
        }
        md = format_markdown(cats, base_tag="v0.1.0", target_tag="v0.2.0")
        self.assertIn("*No changes.*", md)


class TestRemoteUrlAndTagResolution(unittest.TestCase):
    """Tests for remote URL normalization and tag predecessor lookups."""

    def test_remote_url_normalization(self):
        with tempfile.TemporaryDirectory() as td:
            repo_path = Path(td)
            subprocess.run(["git", "init", "-b", "main"], cwd=repo_path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(
                ["git", "remote", "add", "origin", "git@github.com:purrfectsoft/sample.git"],
                cwd=repo_path,
                check=True,
            )
            url = get_repo_remote_url(repo_path)
            self.assertEqual(url, "https://github.com/purrfectsoft/sample")

    def test_remote_url_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            url = get_repo_remote_url(td)
            self.assertEqual(url, DEFAULT_REPO_URL)

    def test_find_previous_tag_none_when_empty(self):
        with tempfile.TemporaryDirectory() as td:
            repo_path = Path(td)
            subprocess.run(["git", "init", "-b", "main"], cwd=repo_path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            prev = find_previous_tag(repo_path, "HEAD")
            self.assertIsNone(prev)


class TestGitHubReleaseSync(unittest.TestCase):
    """Tests for GitHub release creation and updating via gh CLI."""

    @patch("subprocess.run")
    def test_sync_github_release_edit_existing(self, mock_run):
        # View succeeds -> Edit succeeds
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # view
            MagicMock(returncode=0, stdout="", stderr=""),  # edit
        ]
        ok, msg = sync_github_release("v1.0.0", "# Release notes")
        self.assertTrue(ok)
        self.assertIn("Successfully updated", msg)

    @patch("subprocess.run")
    def test_sync_github_release_create_new(self, mock_run):
        # View fails -> Create succeeds
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="not found"),  # view
            MagicMock(returncode=0, stdout="", stderr=""),  # create
        ]
        ok, msg = sync_github_release("v1.0.0-rc1", "# Release notes")
        self.assertTrue(ok)
        self.assertIn("Successfully created", msg)

    @patch("subprocess.run")
    def test_sync_github_release_error_suppressed(self, mock_run):
        # View succeeds -> Edit fails with error
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=1, stdout="", stderr="GraphQL API error: 403"),
        ]
        ok, msg = sync_github_release("v1.0.0", "# Release notes")
        self.assertFalse(ok)
        self.assertIn("Failed to edit", msg)

    @patch("subprocess.run", side_effect=FileNotFoundError("gh not found"))
    def test_sync_github_release_missing_gh_cli(self, mock_run):
        ok, msg = sync_github_release("v1.0.0", "# Release notes")
        self.assertFalse(ok)
        self.assertIn("GitHub CLI ('gh') not found", msg)


class TestReleaseNotesCli(unittest.TestCase):
    """Tests for agyis release-notes CLI command dispatch."""

    def test_cli_release_notes_stdout(self):
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["release-notes", "--base", "v1.0.0-rc4", "--tag", "v1.0.0-rc5"])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertIn("## What's Changed", out)
            self.assertIn("### Features & Architecture", out)
            self.assertIn("feat(cli): unified agyis onboard CLI engine completion (#58)", out)
            self.assertIn("**Full Changelog**: https://github.com/kuasha420/agyis-harness/compare/v1.0.0-rc4...v1.0.0-rc5", out)

    def test_cli_release_notes_output_file(self):
        with tempfile.TemporaryDirectory() as td:
            out_file = Path(td) / "dist" / "NOTES.md"
            with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                code = main([
                    "release-notes",
                    "--base", "v1.0.0-rc4",
                    "--tag", "v1.0.0-rc5",
                    "-o", str(out_file),
                ])
                self.assertEqual(code, 0)
                self.assertTrue(out_file.exists())
                content = out_file.read_text(encoding="utf-8")
                self.assertIn("## What's Changed", content)
                self.assertEqual(mock_out.getvalue(), "")

    def test_cli_release_notes_json(self):
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main([
                "release-notes",
                "--base", "v1.0.0-rc4",
                "--tag", "v1.0.0-rc5",
                "--json",
            ])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue())
            self.assertTrue(data["success"])
            self.assertEqual(data["target_tag"], "v1.0.0-rc5")
            self.assertEqual(data["base_tag"], "v1.0.0-rc4")
            self.assertEqual(data["commits_count"], 19)
            self.assertIn("Features & Architecture", data["categories"])

    @patch("harness.commands.release_notes.sync_github_release")
    def test_cli_release_notes_gh_release_failure_suppressed(self, mock_sync):
        mock_sync.return_value = (False, "Authentication error")
        with patch("sys.stderr", new_callable=io.StringIO) as mock_err, \
             patch("sys.stdout", new_callable=io.StringIO):
            code = main([
                "release-notes",
                "--base", "v1.0.0-rc4",
                "--tag", "v1.0.0-rc5",
                "--gh-release", "v1.0.0-rc5",
            ])
            self.assertEqual(code, 1)
            self.assertIn("Authentication error", mock_err.getvalue())


class TestReleaseNotesIntegration(unittest.TestCase):
    """Sub-second hermetic integration test with synthetic git lifecycle."""

    def test_synthetic_git_repo_generation_subsecond(self):
        t0 = time.perf_counter()
        with tempfile.TemporaryDirectory() as td:
            repo_path = Path(td)
            subprocess.run(
                ["git", "init", "-b", "main"],
                cwd=repo_path,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo_path, check=True)
            subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=repo_path, check=True)

            # Commit 1
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", "feat: initial feature (#1)"],
                cwd=repo_path,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(["git", "tag", "v0.1.0"], cwd=repo_path, check=True)

            # Commit 2
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", "fix(core): remediate bug (#2)"],
                cwd=repo_path,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(["git", "tag", "v0.2.0"], cwd=repo_path, check=True)

            notes = generate_release_notes(
                repo_dir=repo_path,
                base_tag="v0.1.0",
                target_ref="v0.2.0",
            )
            self.assertIn("### Bug Fixes & Hardening", notes)
            self.assertIn("fix(core): remediate bug (#2)", notes)
            self.assertIn("compare/v0.1.0...v0.2.0", notes)

        duration = time.perf_counter() - t0
        self.assertLess(duration, 1.0, f"Benchmark exceeded 1.0s: {duration:.3f}s")


if __name__ == "__main__":
    unittest.main()
