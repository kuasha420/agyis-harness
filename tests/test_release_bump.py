# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Hermetic verification suite for `agyis release` bump engine and CLI (Track 4)."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from harness.cli import build_parser, main as cli_main
from harness.delivery.release_bump import (
    apply_release_bump,
    check_release_parity,
    normalize_release_version,
    plan_release_bump,
)
from harness.delivery.sync_check import count_surface_inventory


def _write_file(base: Path, rel_path: str, content: str) -> Path:
    target = base / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def _populate_rich_release_fixture(root: Path, version: str = "1.1.0", date_str: str = "2026-11-27") -> None:
    """Create a complete hermetic fixture mirroring all release surfaces and strict exclusions."""
    _write_file(
        root,
        "pyproject.toml",
        f'[build-system]\nrequires = ["hatchling"]\n\n[project]\nname = "agyis-harness"\nversion = "{version}"\n',
    )
    _write_file(root, "harness/__init__.py", f'"""Agyis Harness."""\n\n__version__ = "{version}"\n')
    _write_file(root, "plugin.json", json.dumps({"name": "agyis-harness", "version": version}, indent=2) + "\n")
    _write_file(root, "package.json", json.dumps({"name": "agyis-harness", "version": version}, indent=2) + "\n")
    _write_file(
        root,
        "uv.lock",
        f'version = 1\n\n[[package]]\nname = "agyis-harness"\nversion = "{version}"\n',
    )
    _write_file(
        root,
        "CHANGELOG.md",
        (
            "# Changelog\n\nAll notable changes are documented in this file.\n\n---\n\n"
            "## [Unreleased]\n\n"
            "### Bug Fixes & Hardening\n"
            "- fix(hooks): prevent anti-clobber write race\n\n"
            "---\n\n"
            f"## [{version}] - {date_str}\n\n"
            "### Features & Architecture\n"
            "- feat(release): initial baseline\n\n"
            "---\n\n"
            "## [1.0.0] - 2026-11-25\n\n"
            "### Features & Architecture\n"
            "- feat(core): GA launch\n\n"
            f"[Unreleased]: https://github.com/kuasha420/agyis-harness/compare/v{version}...HEAD\n"
            f"[{version}]: https://github.com/kuasha420/agyis-harness/compare/v1.0.0...v{version}\n"
            "[1.0.0]: https://github.com/kuasha420/agyis-harness/commits/v1.0.0\n"
        ),
    )
    _write_file(
        root,
        "website/brand/svg/og-overlay.svg",
        f'<svg><text>Version {version}  ·  agyis-harness.io</text></svg>\n',
    )
    backdrop = root / "website" / "assets" / "art" / "og-backdrop-1-0.png"
    backdrop.parent.mkdir(parents=True, exist_ok=True)
    backdrop.write_bytes(b"\x89PNG\r\n\x1a\n")

    _write_file(
        root,
        "website/index.html",
        (
            f"<title>Agyis Harness {version} | Deterministic guardrails</title>\n"
            f'<meta property="og:title" content="Agyis Harness {version}">\n'
            f'<meta name="twitter:title" content="Agyis Harness {version}">\n'
            f'<p class="hero-copy">Agyis Harness {version} stops loops.</p>\n'
            f'<a href="#install">Install v{version}</a>\n'
            f"<p>Every guardrail in Agyis {version} traces to measurements.</p>\n"
            f"<caption>Version {version} verification ledger &amp; baseline</caption>\n"
            f"<h2>Install Agyis Harness {version}</h2>\n"
            f"<p>Install the frozen v{version} wheel today.</p>\n"
            f'<a href="https://github.com/kuasha420/agyis-harness/releases/tag/v{version}">View v{version} release on GitHub</a>\n'
        ),
    )
    _write_file(
        root,
        "website/cognitive/index.html",
        (
            f"<title>Cognitive Architecture | Agyis Harness {version}</title>\n"
            f'<meta property="og:title" content="Cognitive Architecture | Agyis Harness {version}">\n'
            f'<a href="https://github.com/kuasha420/agyis-harness/releases/tag/v{version}">Releases</a>\n'
        ),
    )
    _write_file(
        root,
        "website/hud-re/index.html",
        (
            f"<title>Trajectory HUD &amp; RE | Agyis Harness {version}</title>\n"
            f'<meta name="twitter:title" content="HUD | Agyis Harness {version}">\n'
            f"<p>Targeting rea@6.9.0 and 2.35.2 RPC parity.</p>\n"
            f'<a href="https://github.com/kuasha420/agyis-harness/releases/tag/v{version}">Releases</a>\n'
        ),
    )
    _write_file(
        root,
        "website/telemetry/index.html",
        (
            f"<title>Telemetry Observatory | Agyis Harness {version}</title>\n"
            "<p>Corpus span: 2026-05-24 to 2026-11-25 UTC | Export schema 1.1.0 | Generated 2026-11-25T23:22:00Z</p>\n"
            "<p>Tracks harness impact across 12 release eras from Pre-Harness baseline through v1.0.0 HEAD.</p>\n"
            f'<a href="https://github.com/kuasha420/agyis-harness/releases/tag/v{version}">Releases</a>\n'
        ),
    )
    _write_file(
        root,
        "website/brand/index.html",
        (
            f"<title>Brand Kit | Agyis Harness {version}</title>\n"
            f'<meta property="og:description" content="Official marks for Agyis Harness {version}.">\n'
            f"<p>1200 x 630 composited social share card for v{version} release links.</p>\n"
            f'<a href="https://github.com/kuasha420/agyis-harness/releases/tag/v{version}">Releases</a>\n'
        ),
    )
    _write_file(
        root,
        "README.md",
        (
            f"[![Version](https://img.shields.io/badge/Version-v{version}-brightgreen.svg)]"
            f"(https://github.com/kuasha420/agyis-harness/releases/tag/v{version})\n"
            f"- **Horizon 0 & 1 (Completed — `v1.0.0` GA -> `v{version}` Uplift)**: done\n"
            f"- **Horizon 2 (Post-`v{version}`)**: upcoming\n"
        ),
    )
    _write_file(
        root,
        "roadmap.md",
        (
            f"**Last Updated**: {date_str} (`v{version}`)\n"
            f"## 3. Completed Baseline (`v{version}` Uplift)\n"
            f"## 4. Post-`v{version}` Horizon 2 Priorities\n"
        ),
    )
    _write_file(
        root,
        "docs/taxonomy/project-ledger.md",
        (
            f"# Agyis Harness Project Ledger (`v{version}` — Compacted)\n\n"
            f"## 1. Current Release Baseline (`v{version}` — {date_str})\n\n"
            "| **`v1.0.0` (GA Launch)** | 2026-11-25 | GA | `2,441` tests |\n"
            f"| **`v{version}` (Uplift)** | {date_str} | Uplift | `2,572` tests |\n"
        ),
    )
    _write_file(root, "docs/user_guide.md", f"**Version**: `{version}` (`{date_str}`)\n")
    _write_file(root, "docs/developer_guide.md", f"**Version**: `{version}` (`{date_str}`)\n")
    _write_file(root, "docs/official-specs/cli-palette.md", f"**Last Updated**: {date_str} (`v{version}`)\n")
    _write_file(root, "docs/official-specs/cockpit-director.md", f"Agyis Harness (`agyis-harness v{version}`)\n")
    _write_file(root, "docs/official-specs/testing-contracts.md", f"**Last Updated**: {date_str} (`v{version}`)\n")
    _write_file(
        root,
        "docs/official-specs/platform-surface-mapping.md",
        f'```json\n{{\n  "name": "agyis-harness",\n  "version": "{version}"\n}}\n```\n',
    )
    _write_file(
        root,
        "docs/runbooks/repo-onboarding.md",
        f"---\nlast_updated: {date_str}\n---\n| **Agyis Harness** | `{version}` | `agyis doctor` |\n",
    )
    _write_file(root, "docs/adr/README.md", f"**Last Updated**: {date_str}\n")
    _write_file(
        root,
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        f'      placeholder: "e.g., {version} or fa8aff2"\n',
    )
    _write_file(
        root,
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        f'      placeholder: "e.g., {version} or fa8aff2"\n',
    )

    # Strict untouched exclusions
    _write_file(root, "server/__init__.py", '__version__ = "1.0.0"\n')
    _write_file(root, "website/data/manifest.json", '{"schema_version": "1.1.0"}\n')
    _write_file(root, "website/telemetry/telemetry.js", 'const label = "Export schema 1.1.0";\n')
    _write_file(root, "harness/runtime/matrix.json", '{"version": "1.0.0"}\n')
    _write_file(root, ".agyis/test_manifest.json", '{"version": "1.1.0"}\n')
    _write_file(root, "docs/archive/old_ledger.md", "# Historical Ledger (`v1.1.0`)\n")


class TestReleaseBump(unittest.TestCase):
    """Contract and regression tests for `agyis release` engine and CLI."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_semver_validation_and_normalization(self) -> None:
        self.assertEqual(normalize_release_version("1.1.1"), "1.1.1")
        self.assertEqual(normalize_release_version("v1.1.1"), "1.1.1")
        self.assertEqual(normalize_release_version("V1.2.0-rc1"), "1.2.0-rc1")
        self.assertEqual(normalize_release_version("2.0.0+build.5"), "2.0.0+build.5")
        for bad in ("", "   ", "1.1", "v1.1", "vv1.1.1", "release-1", "1.2.x"):
            with self.assertRaises(ValueError):
                normalize_release_version(bad)

        with self.assertRaises(ValueError):
            plan_release_bump(self.root, "1.1.1", release_date="2026-13-45")

    def test_dry_run_default_makes_zero_filesystem_mutations(self) -> None:
        _populate_rich_release_fixture(self.root)
        before_pyproject = (self.root / "pyproject.toml").read_text(encoding="utf-8")
        before_changelog = (self.root / "CHANGELOG.md").read_text(encoding="utf-8")

        with patch("harness.delivery.release_bump.shutil.which", return_value=None):
            res = apply_release_bump(self.root, "v1.1.1", apply=False, release_date="2026-11-28")

        self.assertTrue(res.dry_run)
        self.assertFalse(res.applied)
        self.assertTrue(res.changed)
        self.assertEqual(res.written_files, [])
        self.assertIn("pyproject.toml", res.changed_files)
        self.assertIn("CHANGELOG.md", res.changed_files)
        self.assertEqual((self.root / "pyproject.toml").read_text(encoding="utf-8"), before_pyproject)
        self.assertEqual((self.root / "CHANGELOG.md").read_text(encoding="utf-8"), before_changelog)

    def test_apply_updates_all_surfaces_preserves_exclusions_and_is_idempotent(self) -> None:
        _populate_rich_release_fixture(self.root)
        # Pre-bump parity must PASS on 1.1.0 (verifying README.md Shields.io badge extractor)
        pre_parity = check_release_parity(self.root, version="1.1.0", include_site=True)
        self.assertEqual(pre_parity["status"], "PASS", f"Pre-bump mismatches: {pre_parity['mismatches']}")

        exclusions = {
            rel: (self.root / rel).read_text(encoding="utf-8")
            for rel in (
                "server/__init__.py",
                "website/data/manifest.json",
                "website/telemetry/telemetry.js",
                "harness/runtime/matrix.json",
                ".agyis/test_manifest.json",
                "docs/archive/old_ledger.md",
            )
        }

        executed_cmds: list[list[str]] = []

        def _fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if cmd[0] == "git":
                return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="not a git repository")
            executed_cmds.append(list(cmd))
            if cmd[:2] == ["uv", "lock"]:
                _write_file(
                    self.root,
                    "uv.lock",
                    'version = 1\n\n[[package]]\nname = "agyis-harness"\nversion = "1.1.1"\n',
                )
            elif cmd[0] == "rsvg-convert":
                Path(cmd[-1]).write_bytes(b"PNG_OVERLAY")
            elif cmd[0] == "magick":
                payload = b"COMPOSED_WEBP" if str(cmd[-1]).endswith(".webp") else b"COMPOSED_PNG"
                Path(cmd[-1]).write_bytes(payload)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with (
            patch("harness.delivery.release_bump.shutil.which", side_effect=lambda b: f"/usr/bin/{b}"),
            patch("harness.delivery.release_bump.subprocess.run", side_effect=_fake_run),
        ):
            res = apply_release_bump(self.root, "1.1.1", apply=True, release_date="2026-11-28")

        self.assertFalse(res.dry_run)
        self.assertTrue(res.applied)
        self.assertGreaterEqual(len(res.written_files), 20)

        # External actions executed: uv lock + rsvg-convert + 2 magick invocations
        action_map = {a.name: a for a in res.actions}
        self.assertEqual(action_map["uv_lock"].status, "executed")
        self.assertEqual(action_map["og_raster"].status, "executed")
        self.assertEqual([c[0] for c in executed_cmds], ["uv", "rsvg-convert", "magick", "magick"])
        self.assertEqual((self.root / "website" / "assets" / "og-image.png").read_bytes(), b"COMPOSED_PNG")
        self.assertEqual((self.root / "website" / "assets" / "og-image.webp").read_bytes(), b"COMPOSED_WEBP")

        # Core manifests updated
        self.assertIn('version = "1.1.1"', (self.root / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertIn('__version__ = "1.1.1"', (self.root / "harness" / "__init__.py").read_text(encoding="utf-8"))
        self.assertEqual(json.loads((self.root / "plugin.json").read_text(encoding="utf-8"))["version"], "1.1.1")
        self.assertEqual(json.loads((self.root / "package.json").read_text(encoding="utf-8"))["version"], "1.1.1")

        # CHANGELOG updated with fresh Unreleased, new 1.1.1 section, updated compare links, and intact history
        cl_text = (self.root / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## [Unreleased]\n\n*No changes.*", cl_text)
        self.assertIn("## [1.1.1] - 2026-11-28", cl_text)
        self.assertIn("## [1.1.0] - 2026-11-27", cl_text)
        self.assertIn("## [1.0.0] - 2026-11-25", cl_text)
        self.assertIn("[Unreleased]: https://github.com/kuasha420/agyis-harness/compare/v1.1.1...HEAD", cl_text)
        self.assertIn("[1.1.1]: https://github.com/kuasha420/agyis-harness/compare/v1.1.0...v1.1.1", cl_text)

        # OG SVG & all 5 website routes updated while preserving Export schema & historical v1.0.0 HEAD
        self.assertIn("Version 1.1.1  ·  agyis-harness.io", (self.root / "website/brand/svg/og-overlay.svg").read_text(encoding="utf-8"))
        for rel_html in (
            "website/index.html",
            "website/cognitive/index.html",
            "website/hud-re/index.html",
            "website/telemetry/index.html",
            "website/brand/index.html",
        ):
            html = (self.root / rel_html).read_text(encoding="utf-8")
            self.assertIn("Agyis Harness 1.1.1", html)
            self.assertIn("/releases/tag/v1.1.1", html)
        telemetry_html = (self.root / "website/telemetry/index.html").read_text(encoding="utf-8")
        self.assertIn("Export schema 1.1.0", telemetry_html)
        self.assertIn("through v1.0.0 HEAD", telemetry_html)

        # Project ledger updated header/baseline but preserved historical rows
        ledger = (self.root / "docs/taxonomy/project-ledger.md").read_text(encoding="utf-8")
        self.assertIn("# Agyis Harness Project Ledger (`v1.1.1` — Compacted)", ledger)
        self.assertIn("## 1. Current Release Baseline (`v1.1.1` — 2026-11-28)", ledger)
        self.assertIn("| **`v1.1.0` (Uplift)** | 2026-11-27 | Uplift | `2,572` tests |", ledger)
        self.assertIn("| **`v1.0.0` (GA Launch)** | 2026-11-25 | GA | `2,441` tests |", ledger)

        # Strict exclusions completely untouched
        for rel, orig_body in exclusions.items():
            self.assertEqual((self.root / rel).read_text(encoding="utf-8"), orig_body, f"Exclusion mutated: {rel}")

        # Idempotency: immediate repeat --dry-run reports 0 pending text edits
        with patch("harness.delivery.release_bump.shutil.which", return_value=None):
            second = apply_release_bump(self.root, "1.1.1", apply=False, release_date="2026-11-28")
        self.assertFalse(second.changed, f"Unexpected non-idempotent edits: {second.changed_files}")
        self.assertEqual(second.changed_files, [])

        # README.md Shields.io badge preserves color/extension suffix
        readme_text = (self.root / "README.md").read_text(encoding="utf-8")
        self.assertIn("badge/Version-v1.1.1-brightgreen.svg", readme_text)

        # Release parity check passes cleanly after apply
        parity = check_release_parity(self.root, version="1.1.1", include_site=True)
        self.assertEqual(parity["status"], "PASS", f"Unexpected mismatches: {parity['mismatches']}")
        self.assertTrue(parity["changelog_has_version"])

        # Prerelease bump preserves Shields.io color/extension suffix and passes parity check
        prerelease_root = self.root / "prerelease_case"
        prerelease_root.mkdir()
        _populate_rich_release_fixture(prerelease_root, version="1.1.0")

        def _fake_prerelease_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if cmd[0] == "git":
                return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="not a git repository")
            if cmd[:2] == ["uv", "lock"]:
                _write_file(
                    prerelease_root,
                    "uv.lock",
                    'version = 1\n\n[[package]]\nname = "agyis-harness"\nversion = "1.2.0-rc1"\n',
                )
            elif cmd[0] == "rsvg-convert":
                Path(cmd[-1]).write_bytes(b"PNG_OVERLAY")
            elif cmd[0] == "magick":
                Path(cmd[-1]).write_bytes(b"COMPOSED")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with (
            patch("harness.delivery.release_bump.shutil.which", side_effect=lambda b: f"/usr/bin/{b}"),
            patch("harness.delivery.release_bump.subprocess.run", side_effect=_fake_prerelease_run),
        ):
            apply_release_bump(prerelease_root, "1.2.0-rc1", apply=True, release_date="2026-11-29")

        prerelease_readme = (prerelease_root / "README.md").read_text(encoding="utf-8")
        self.assertIn("badge/Version-v1.2.0-rc1-brightgreen.svg", prerelease_readme)
        prerelease_parity = check_release_parity(prerelease_root, version="1.2.0-rc1", include_site=True)
        self.assertEqual(
            prerelease_parity["status"],
            "PASS",
            f"Prerelease mismatches: {prerelease_parity['mismatches']}",
        )

    def test_graceful_skip_when_binaries_absent_and_skip_flags(self) -> None:
        _populate_rich_release_fixture(self.root)
        with patch("harness.delivery.release_bump.shutil.which", return_value=None):
            res_missing = apply_release_bump(self.root, "1.1.1", apply=True, release_date="2026-11-28")
        actions_missing = {a.name: a for a in res_missing.actions}
        self.assertEqual(actions_missing["uv_lock"].status, "skipped")
        self.assertEqual(actions_missing["og_raster"].status, "skipped")
        self.assertGreaterEqual(len(res_missing.warnings), 2)

        # Skip flags honor --skip-og, --skip-lock, --skip-changelog
        tmp2 = self.root / "skip_case"
        tmp2.mkdir()
        _populate_rich_release_fixture(tmp2)
        orig_cl = (tmp2 / "CHANGELOG.md").read_text(encoding="utf-8")
        orig_og = (tmp2 / "website/brand/svg/og-overlay.svg").read_text(encoding="utf-8")
        res_skip = apply_release_bump(
            tmp2,
            "1.1.2",
            apply=True,
            release_date="2026-11-29",
            skip_og=True,
            skip_lock=True,
            skip_changelog=True,
        )
        self.assertEqual((tmp2 / "CHANGELOG.md").read_text(encoding="utf-8"), orig_cl)
        self.assertEqual((tmp2 / "website/brand/svg/og-overlay.svg").read_text(encoding="utf-8"), orig_og)
        self.assertEqual({a.name: a.status for a in res_skip.actions}, {"uv_lock": "skipped", "og_raster": "skipped"})

    def test_cli_wiring_subparser_count_and_release_check_failure_detection(self) -> None:
        surface = count_surface_inventory(Path(__file__).resolve().parent.parent)
        self.assertEqual(surface["cli_subparsers"], 32)
        self.assertEqual(surface["cli_logical_subcommands"], 31)

        parser = build_parser()
        parsed_bump = parser.parse_args(["release", "bump", "1.1.1", "--skip-og", "--json"])
        self.assertEqual(parsed_bump.subcommand, "release")
        self.assertEqual(parsed_bump.release_action, "bump")
        self.assertEqual(parsed_bump.version, "1.1.1")
        self.assertFalse(parsed_bump.apply)

        # --dry-run and --apply must be mutually exclusive
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["release", "bump", "1.1.1", "--dry-run", "--apply"])

        _populate_rich_release_fixture(self.root, version="1.1.0")
        out_buf = io.StringIO()
        with contextlib.redirect_stdout(out_buf):
            rc = cli_main(["release", "check", "--version", "1.1.1", "--workspace", str(self.root), "--include-site", "--json"])
        self.assertEqual(rc, 1)
        payload = json.loads(out_buf.getvalue())
        self.assertEqual(payload["status"], "FAIL")
        self.assertFalse(payload["changelog_has_version"])
        self.assertTrue(any("Expected version '1.1.1'" in m for m in payload["mismatches"]))


if __name__ == "__main__":
    unittest.main()
