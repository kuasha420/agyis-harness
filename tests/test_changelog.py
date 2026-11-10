#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic test suite for native Keep-a-Changelog generator and CLI (`agyis changelog`).
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
from unittest.mock import patch

from harness.cli import main
from harness.delivery.changelog import (
    backfill_changelog,
    format_changelog_section,
    generate_changelog,
    normalize_changelog_version,
    parse_changelog_document,
    upsert_changelog_document,
)
from harness.delivery.release_notes import (
    CATEGORY_DOCS,
    CATEGORY_FEATURES,
    CATEGORY_FIXES,
    CATEGORY_MAINTENANCE,
)


def _git(repo: Path, *args: str, env_extra: dict[str, str] | None = None) -> str:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def _init_repo(repo: Path) -> None:
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Tester")
    _git(repo, "config", "user.email", "tester@example.com")
    _git(repo, "remote", "add", "origin", "https://github.com/purrfectsoft/demo-repo.git")


def _commit(repo: Path, message: str, ts: str = "2026-10-15T12:00:00Z") -> None:
    env = {"GIT_AUTHOR_DATE": ts, "GIT_COMMITTER_DATE": ts}
    _git(repo, "commit", "--allow-empty", "-m", message, env_extra=env)


class TestChangelogFormattingAndUpsert(unittest.TestCase):
    """Unit tests for version normalization, Keep-a-Changelog rendering, and document upsert."""

    def test_normalize_changelog_version(self):
        self.assertEqual(normalize_changelog_version(None), "Unreleased")
        self.assertEqual(normalize_changelog_version("Unreleased"), "Unreleased")
        self.assertEqual(normalize_changelog_version("unreleased"), "Unreleased")
        self.assertEqual(normalize_changelog_version("HEAD"), "Unreleased")
        self.assertEqual(normalize_changelog_version("v1.0.0-rc5"), "1.0.0-rc5")
        self.assertEqual(normalize_changelog_version("1.0.0-rc10"), "1.0.0-rc10")
        self.assertEqual(normalize_changelog_version("V2.1.0"), "2.1.0")

    def test_format_changelog_section_canonical_and_keepachangelog(self):
        cats = {
            CATEGORY_FEATURES: [
                {
                    "hash": "abc",
                    "subject": "feat(api)!: new endpoint",
                    "breaking": True,
                    "sub_bullets": ["Adds breaking route"],
                }
            ],
            CATEGORY_FIXES: [{"hash": "def", "subject": "fix: resolve leak", "breaking": False}],
            CATEGORY_DOCS: [{"hash": "ghi", "subject": "docs: update guide", "breaking": False}],
            CATEGORY_MAINTENANCE: [{"hash": "jkl", "subject": "chore: tidy scripts", "breaking": False}],
        }
        canonical = format_changelog_section(cats, "v1.2.0", release_date="2026-11-10")
        self.assertIn("## [1.2.0] - 2026-11-10", canonical)
        self.assertLess(canonical.index("### Breaking Changes"), canonical.index("### Features & Architecture"))
        self.assertIn("### Bug Fixes & Hardening", canonical)
        self.assertIn("  - Adds breaking route", canonical)

        kac = format_changelog_section(cats, None, style="keepachangelog")
        self.assertTrue(kac.startswith("## [Unreleased]"))
        self.assertIn("### Breaking Changes", kac)
        self.assertIn("### Added", kac)
        self.assertIn("### Changed", kac)
        self.assertIn("### Fixed", kac)
        self.assertIn("docs: update guide", kac)
        self.assertIn("chore: tidy scripts", kac)

    def test_upsert_preserves_spdx_preamble_and_historical_sections_with_semver_desc(self):
        existing = (
            "<!-- SPDX-License-Identifier: Apache-2.0 -->\n"
            "<!-- Custom Header -->\n\n"
            "# Changelog\n\n"
            "Custom intro.\n\n"
            "---\n\n"
            "## [1.0.0-rc2] - 2026-10-14\n\n"
            "### Features & Architecture\n"
            "- Handcrafted rc2 note\n\n"
            "---\n\n"
            "## [1.0.0-rc0] - 2026-10-12\n\n"
            "### Features & Initial Release\n"
            "- Handcrafted rc0 note\n"
        )
        updated = upsert_changelog_document(
            existing_content=existing,
            updates={
                "Unreleased": "## [Unreleased]\n\n### Features & Architecture\n- feat: unreleased",
                "v1.0.0-rc10": "## [1.0.0-rc10] - 2026-11-10\n\n### Features & Architecture\n- feat: rc10",
                "v1.0.0-rc9": "## [1.0.0-rc9] - 2026-11-03\n\n### Fixes\n- fix: rc9",
            },
            link_updates={
                "Unreleased": "https://github.com/purrfectsoft/demo-repo/compare/v1.0.0-rc10...HEAD",
                "1.0.0-rc10": "https://github.com/purrfectsoft/demo-repo/compare/v1.0.0-rc9...v1.0.0-rc10",
                "1.0.0-rc9": "https://github.com/purrfectsoft/demo-repo/compare/v1.0.0-rc2...v1.0.0-rc9",
                "1.0.0-rc2": "https://github.com/purrfectsoft/demo-repo/compare/v1.0.0-rc0...v1.0.0-rc2",
                "1.0.0-rc0": "https://github.com/purrfectsoft/demo-repo/commits/v1.0.0-rc0",
            },
        )
        self.assertTrue(updated.startswith("<!-- SPDX-License-Identifier: Apache-2.0 -->\n<!-- Custom Header -->"))
        self.assertIn("- Handcrafted rc2 note", updated)
        self.assertIn("- Handcrafted rc0 note", updated)

        # Verify section ordering: Unreleased -> rc10 -> rc9 -> rc2 -> rc0
        idx_u = updated.index("## [Unreleased]")
        idx_10 = updated.index("## [1.0.0-rc10]")
        idx_9 = updated.index("## [1.0.0-rc9]")
        idx_2 = updated.index("## [1.0.0-rc2]")
        idx_0 = updated.index("## [1.0.0-rc0]")
        self.assertTrue(idx_u < idx_10 < idx_9 < idx_2 < idx_0)

        # Verify footer links deduplicated & sorted in same order
        link_u = updated.index("[Unreleased]: https://")
        link_10 = updated.index("[1.0.0-rc10]: https://")
        link_9 = updated.index("[1.0.0-rc9]: https://")
        link_2 = updated.index("[1.0.0-rc2]: https://")
        link_0 = updated.index("[1.0.0-rc0]: https://")
        self.assertTrue(link_u < link_10 < link_9 < link_2 < link_0)

        # Second pass produces identical bytes
        _, secs, links = parse_changelog_document(updated)
        self.assertEqual(set(secs.keys()), {"Unreleased", "1.0.0-rc10", "1.0.0-rc9", "1.0.0-rc2", "1.0.0-rc0"})
        self.assertEqual(len(links), 5)


class TestChangelogBackfillAndCli(unittest.TestCase):
    """Sub-second hermetic integration tests for `agyis changelog` and `changelogs` alias."""

    def test_backfill_rc0_through_rc9_and_unreleased_idempotent_subsecond(self):
        t0 = time.perf_counter()
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _init_repo(repo)

            # Create rc0..rc9 tags mixing annotated and lightweight tags
            for i in range(10):
                day = 10 + i
                ts = f"2026-10-{day:02d}T10:00:00Z"
                _commit(repo, f"feat(core): milestone rc{i} (#{i + 1})", ts=ts)
                tag = f"v1.0.0-rc{i}"
                if i % 2 == 0:
                    _git(repo, "tag", "-a", tag, "-m", f"Release {tag}", env_extra={"GIT_COMMITTER_DATE": ts})
                else:
                    _git(repo, "tag", tag)

            # Add unreleased commits after rc9 (one with hyphen breaking footer)
            _commit(
                repo,
                "feat(cli): add changelog engine\n\nBREAKING-CHANGE: dropped legacy flag",
                ts="2026-10-25T10:00:00Z",
            )

            changelog_file = repo / "CHANGELOG.md"
            changelog_file.write_text(
                "<!-- SPDX-License-Identifier: Apache-2.0 -->\n\n"
                "# Changelog\n\n"
                "---\n\n"
                "## [1.0.0-rc1] - 2026-10-11\n\n"
                "### Features & Architecture\n"
                "- Preserved custom rc1 entry\n\n"
                "---\n\n"
                "## [1.0.0-rc0] - 2026-10-10\n\n"
                "### Features & Initial Release\n"
                "- Preserved custom rc0 entry\n",
                encoding="utf-8",
            )

            with patch("sys.stdout", new_callable=io.StringIO) as out1:
                rc1 = main(["changelog", "-w", str(repo), "--backfill", "--write"])
                self.assertEqual(rc1, 0)
                self.assertIn("Updated", out1.getvalue())

            first_pass = changelog_file.read_text(encoding="utf-8")
            self.assertTrue(first_pass.startswith("<!-- SPDX-License-Identifier: Apache-2.0 -->"))
            self.assertIn("- Preserved custom rc1 entry", first_pass)
            self.assertIn("- Preserved custom rc0 entry", first_pass)
            self.assertIn("## [Unreleased]", first_pass)
            self.assertIn("### Breaking Changes", first_pass)
            self.assertIn("feat(cli): add changelog engine", first_pass)
            for i in range(2, 10):
                self.assertIn(f"## [1.0.0-rc{i}] - 2026-10-{10 + i:02d}", first_pass)
            self.assertIn(
                "[Unreleased]: https://github.com/purrfectsoft/demo-repo/compare/v1.0.0-rc9...HEAD",
                first_pass,
            )
            self.assertIn(
                "[1.0.0-rc0]: https://github.com/purrfectsoft/demo-repo/commits/v1.0.0-rc0",
                first_pass,
            )

            # Second backfill write must be completely idempotent
            with patch("sys.stdout", new_callable=io.StringIO):
                rc2 = main(["changelogs", "-w", str(repo), "--backfill", "--write"])
                self.assertEqual(rc2, 0)

            second_pass = changelog_file.read_text(encoding="utf-8")
            self.assertEqual(first_pass, second_pass)

        self.assertLess(time.perf_counter() - t0, 1.0)

    def test_cli_changelogs_alias_json_file_date_version_repo_url(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _init_repo(repo)
            _commit(repo, "feat: initial", ts="2026-10-01T10:00:00Z")
            _git(repo, "tag", "v1.0.0-rc9")
            _commit(repo, "fix(cli): repair parser (#99)", ts="2026-10-02T10:00:00Z")

            custom_file = repo / "docs" / "HISTORY.md"
            with patch("sys.stdout", new_callable=io.StringIO) as out:
                code = main([
                    "changelogs",
                    "-w", str(repo),
                    "--version", "v1.0.0-rc10",
                    "--base", "v1.0.0-rc9",
                    "--date", "2026-11-10",
                    "--file", str(custom_file),
                    "--repo-url", "https://github.com/acme/custom",
                    "--write",
                    "--json",
                ])
                self.assertEqual(code, 0)
                payload = json.loads(out.getvalue())

            self.assertTrue(payload["success"])
            self.assertTrue(payload["written"])
            self.assertEqual(payload["version"], "1.0.0-rc10")
            self.assertEqual(payload["release_date"], "2026-11-10")
            self.assertEqual(payload["commits_count"], 1)
            self.assertEqual(
                payload["compare_url"],
                "https://github.com/acme/custom/compare/v1.0.0-rc9...v1.0.0-rc10",
            )
            self.assertTrue(custom_file.exists())
            content = custom_file.read_text(encoding="utf-8")
            self.assertIn("## [1.0.0-rc10] - 2026-11-10", content)
            self.assertIn("fix(cli): repair parser (#99)", content)
            self.assertIn(
                "[1.0.0-rc10]: https://github.com/acme/custom/compare/v1.0.0-rc9...v1.0.0-rc10",
                content,
            )

    def test_cli_changelog_default_unreleased_and_invalid_refs_exit_1(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _init_repo(repo)
            _commit(repo, "feat: baseline", ts="2026-10-01T10:00:00Z")
            _git(repo, "tag", "v1.0.0")
            _commit(repo, "docs: document api", ts="2026-10-02T10:00:00Z")

            with patch("sys.stdout", new_callable=io.StringIO) as out:
                code = main(["changelog", "-w", str(repo)])
                self.assertEqual(code, 0)
                text = out.getvalue()
                self.assertIn("## [Unreleased]", text)
                self.assertIn("docs: document api", text)
                self.assertFalse((repo / "CHANGELOG.md").exists())

            with self.assertRaises(ValueError):
                generate_changelog(repo_dir=repo, base_tag="v9.9.9-missing")
            with self.assertRaises(ValueError):
                generate_changelog(repo_dir=repo, target_rev="missing-branch")
            with self.assertRaises(ValueError):
                backfill_changelog(repo_dir=repo, target_rev="missing-branch")

            with patch("sys.stderr", new_callable=io.StringIO) as err:
                bad_base_rc = main(["changelog", "-w", str(repo), "--base", "does-not-exist"])
                self.assertEqual(bad_base_rc, 1)
                self.assertIn("Invalid base ref", err.getvalue())

            with patch("sys.stderr", new_callable=io.StringIO) as err:
                bad_rev_rc = main(["changelog", "-w", str(repo), "--rev", "does-not-exist"])
                self.assertEqual(bad_rev_rc, 1)
                self.assertIn("Invalid target revision ref", err.getvalue())


if __name__ == "__main__":
    unittest.main()
