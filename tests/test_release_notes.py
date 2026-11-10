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
import harness.delivery as delivery_pkg
from harness.delivery.release_notes import (
    CATEGORY_BREAKING,
    CATEGORY_DOCS,
    CATEGORY_FEATURES,
    CATEGORY_FIXES,
    CATEGORY_MAINTENANCE,
    DEFAULT_REPO_URL,
    categorize_commits,
    collect_release_notes,
    extract_issue_references,
    find_previous_tag,
    format_markdown,
    generate_release_notes,
    get_repo_remote_url,
    get_tag_date,
    list_release_tags,
    parse_commit_record,
    parse_commits,
    parse_semver_tag,
    resolve_git_ref,
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


class TestBreakingChangesAndPublicExports(unittest.TestCase):
    """Tests for breaking footer variants, section placement, and backwards-compatible exports."""

    def test_hyphen_and_non_conventional_breaking_footers(self):
        hyphen_rec = "1111111\x1ffix(auth): rotate tokens\x1fBREAKING-CHANGE: old token rejected\x1e"
        non_conv_rec = "2222222\x1fDrop legacy sync endpoint\x1fBREAKING CHANGE: endpoint removed\x1e"
        non_conv_hyphen = "3333333\x1fRemove v1 config\x1fBREAKING-CHANGE: v1 config ignored\x1e"

        commits = parse_commits(hyphen_rec + non_conv_rec + non_conv_hyphen)
        self.assertEqual(len(commits), 3)
        self.assertTrue(all(c["breaking"] for c in commits))

        cats = categorize_commits(commits)
        self.assertEqual(set(cats.keys()), {
            CATEGORY_FEATURES,
            CATEGORY_FIXES,
            CATEGORY_DOCS,
            CATEGORY_MAINTENANCE,
        })

        # Deduplication when commit appears in both CATEGORY_BREAKING and SECTION_ORDER
        cats_with_extra = dict(cats)
        cats_with_extra[CATEGORY_BREAKING] = [commits[0]]
        md = format_markdown(cats_with_extra, base_tag="v1.0.0", target_tag="v2.0.0")

        self.assertIn("### Breaking Changes", md)
        idx_changed = md.index("## What's Changed")
        idx_breaking = md.index("### Breaking Changes")
        idx_fixes = md.index("### Bug Fixes & Hardening")
        idx_maint = md.index("### Maintenance & Release")
        self.assertTrue(idx_changed < idx_breaking < idx_fixes < idx_maint)
        # Breaking commit remains in its primary SECTION_ORDER bucket too and is deduplicated in Breaking Changes
        self.assertEqual(md.count("- fix(auth): rotate tokens"), 2)

    def test_non_breaking_markdown_unchanged(self):
        cats = {
            CATEGORY_FEATURES: [{"subject": "feat: clean addition", "breaking": False}],
            CATEGORY_FIXES: [],
            CATEGORY_DOCS: [],
            CATEGORY_MAINTENANCE: [],
        }
        md = format_markdown(cats, base_tag="v1.0.0", target_tag="v1.1.0")
        expected = (
            "# Release v1.1.0\n\n"
            "## What's Changed\n\n"
            "### Features & Architecture\n"
            "- feat: clean addition\n\n"
            "**Full Changelog**: https://github.com/kuasha420/agyis-harness/compare/v1.0.0...v1.1.0\n"
        )
        self.assertEqual(md, expected)

    def test_backwards_compatible_20_exports(self):
        expected_20 = {
            "CATEGORY_DOCS",
            "CATEGORY_FEATURES",
            "CATEGORY_FIXES",
            "CATEGORY_MAINTENANCE",
            "CONVENTIONAL_COMMIT_REGEX",
            "CommitInfo",
            "DEFAULT_REPO_URL",
            "ISSUE_EXTRACTION_REGEX",
            "ReleaseNotesResult",
            "SECTION_ORDER",
            "TYPE_TO_CATEGORY",
            "categorize_commits",
            "extract_issue_references",
            "find_previous_tag",
            "format_markdown",
            "generate_release_notes",
            "get_repo_remote_url",
            "parse_commit_record",
            "parse_commits",
            "sync_github_release",
        }
        import harness.delivery.release_notes as rn_mod

        self.assertTrue(expected_20.issubset(set(rn_mod.__all__)))
        self.assertTrue(expected_20.issubset(set(delivery_pkg.__all__)))


class TestTagOrderingAndRefValidation(unittest.TestCase):
    """Tests for SemVer numeric ordering, lightweight/annotated tags, and ref validation."""

    def test_semver_ordering_rc2_rc9_rc10_stable(self):
        tags = ["v1.0.0", "v1.0.0-rc10", "v1.0.0-rc2", "v1.0.0-rc9", "v1.0.0-alpha.1", "v1.0.0-rc0"]
        ordered = sorted(tags, key=lambda t: parse_semver_tag(t))
        self.assertEqual(
            ordered,
            ["v1.0.0-alpha.1", "v1.0.0-rc0", "v1.0.0-rc2", "v1.0.0-rc9", "v1.0.0-rc10", "v1.0.0"],
        )

    def test_lightweight_annotated_tags_and_find_previous_tag(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=repo, check=True)

            # Unborn repo returns empty ReleaseNotesResult when base_tag is None
            unborn_res = collect_release_notes(repo, target_ref="v0.1.0")
            self.assertEqual(unborn_res.commits_count, 0)
            self.assertIn("*No changes.*", unborn_res.markdown)

            def commit_and_tag(msg: str, tag: str, ts: str, annotated: bool) -> None:
                env = os.environ | {"GIT_AUTHOR_DATE": ts, "GIT_COMMITTER_DATE": ts}
                subprocess.run(
                    ["git", "commit", "--allow-empty", "-m", msg],
                    cwd=repo,
                    env=env,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if annotated:
                    subprocess.run(["git", "tag", "-a", tag, "-m", tag], cwd=repo, env=env, check=True)
                else:
                    subprocess.run(["git", "tag", tag], cwd=repo, env=env, check=True)

            commit_and_tag("feat: rc2", "v1.0.0-rc2", "2026-10-02T10:00:00Z", annotated=False)
            commit_and_tag("feat: rc9", "v1.0.0-rc9", "2026-10-09T10:00:00Z", annotated=True)
            commit_and_tag("feat: rc10", "v1.0.0-rc10", "2026-10-10T10:00:00Z", annotated=False)
            # Co-locate v1.0.0 with v1.0.0-rc10 on the same commit
            subprocess.run(["git", "tag", "-a", "v1.0.0", "-m", "v1.0.0"], cwd=repo, env=os.environ | {"GIT_COMMITTER_DATE": "2026-10-11T10:00:00Z"}, check=True)

            self.assertEqual(
                list_release_tags(repo),
                ["v1.0.0-rc2", "v1.0.0-rc9", "v1.0.0-rc10", "v1.0.0"],
            )
            self.assertEqual(get_tag_date(repo, "v1.0.0-rc9"), "2026-10-09")
            self.assertEqual(get_tag_date(repo, "v1.0.0-rc2"), "2026-10-02")

            self.assertEqual(find_previous_tag(repo, "v1.0.0-rc10"), "v1.0.0-rc9")
            self.assertEqual(find_previous_tag(repo, "v1.0.0"), "v1.0.0-rc10")
            # HEAD sitting on co-located tags excludes all co-located tags
            self.assertEqual(find_previous_tag(repo, "HEAD"), "v1.0.0-rc9")

            # Add commit ahead of v1.0.0
            env_next = os.environ | {"GIT_AUTHOR_DATE": "2026-10-12T10:00:00Z", "GIT_COMMITTER_DATE": "2026-10-12T10:00:00Z"}
            subprocess.run(["git", "commit", "--allow-empty", "-m", "feat: next release"], cwd=repo, env=env_next, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            head_sha = resolve_git_ref(repo, "HEAD")
            self.assertIsNotNone(head_sha)
            self.assertEqual(find_previous_tag(repo, "HEAD"), "v1.0.0")

            # Untagged future tag defaults --rev to HEAD
            future_res = collect_release_notes(repo, target_ref="v1.0.1")
            self.assertEqual(future_res.base_tag, "v1.0.0")
            self.assertEqual(future_res.target_tag, "v1.0.1")
            self.assertEqual(future_res.commits_count, 1)
            self.assertIn("feat: next release", future_res.markdown)

            # Explicit --rev works and invalid --base / --rev fail loudly
            rev_res = collect_release_notes(repo, base_tag="v1.0.0-rc9", target_ref="v1.0.0-rc10", target_rev="v1.0.0-rc10")
            self.assertEqual(rev_res.commits_count, 1)
            with self.assertRaises(ValueError):
                collect_release_notes(repo, base_tag="invalid-ref")
            with self.assertRaises(ValueError):
                collect_release_notes(repo, target_rev="invalid-ref")

            with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                self.assertEqual(main(["release-notes", "-w", str(repo), "--base", "bad-ref"]), 1)
                self.assertIn("Invalid base ref", mock_err.getvalue())
            with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                self.assertEqual(main(["release-notes", "-w", str(repo), "--rev", "bad-ref"]), 1)
                self.assertIn("Invalid target revision ref", mock_err.getvalue())


class TestHardenedSyncAndCliFlags(unittest.TestCase):
    """Tests for hardened sync_github_release() and new CLI release-notes flags."""

    @patch("subprocess.run")
    def test_sync_edit_with_title_prerelease_and_assets(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # view
            MagicMock(returncode=0, stdout="", stderr=""),  # upload --clobber
            MagicMock(returncode=0, stdout="", stderr=""),  # edit
        ]
        ok, msg = sync_github_release(
            "v1.0.0",
            "# Notes",
            prerelease=False,
            title="Release 1.0.0",
            assets=["dist/pkg.whl"],
        )
        self.assertTrue(ok)
        self.assertIn("Successfully updated", msg)
        upload_cmd = mock_run.call_args_list[1].args[0]
        edit_cmd = mock_run.call_args_list[2].args[0]
        self.assertEqual(upload_cmd, ["gh", "release", "upload", "v1.0.0", "dist/pkg.whl", "--clobber"])
        self.assertIn("--title", edit_cmd)
        self.assertIn("Release 1.0.0", edit_cmd)
        self.assertIn("--prerelease=false", edit_cmd)

    @patch("subprocess.run")
    def test_sync_collision_fallback_uploads_and_edits(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="release not found"),  # view
            MagicMock(returncode=1, stdout="", stderr="HTTP 422 release_already_exists"),  # create fails
            MagicMock(returncode=0, stdout="", stderr=""),  # upload --clobber
            MagicMock(returncode=0, stdout="", stderr=""),  # edit fallback
        ]
        ok, msg = sync_github_release(
            "v1.0.0-rc10",
            "# Notes",
            prerelease=True,
            title="RC10",
            assets=["dist/a.whl", "dist/b.tar.gz"],
        )
        self.assertTrue(ok)
        self.assertIn("Successfully updated", msg)
        upload_cmd = mock_run.call_args_list[2].args[0]
        edit_cmd = mock_run.call_args_list[3].args[0]
        self.assertEqual(upload_cmd, ["gh", "release", "upload", "v1.0.0-rc10", "dist/a.whl", "dist/b.tar.gz", "--clobber"])
        self.assertIn("--title", edit_cmd)
        self.assertIn("RC10", edit_cmd)
        self.assertIn("--prerelease", edit_cmd)

    @patch("harness.commands.release_notes.sync_github_release")
    def test_cli_forwards_title_prerelease_and_no_prerelease(self, mock_sync):
        mock_sync.return_value = (True, "ok")
        with patch("sys.stdout", new_callable=io.StringIO):
            code = main([
                "release-notes",
                "--base", "v1.0.0-rc4",
                "--tag", "v1.0.0-rc5",
                "--rev", "v1.0.0-rc5",
                "--gh-release", "v1.0.0-rc5",
                "--title", "Custom RC5",
                "--no-prerelease",
            ])
        self.assertEqual(code, 0)
        self.assertEqual(mock_sync.call_args.kwargs["title"], "Custom RC5")
        self.assertFalse(mock_sync.call_args.kwargs["prerelease"])


if __name__ == "__main__":
    unittest.main()
