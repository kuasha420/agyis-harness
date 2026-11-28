# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Hermetic verification suite for uplifted `sync_check` and CI/Release workflow gates (Track 4)."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from harness.delivery.sync_check import (
    count_surface_inventory,
    format_sync_check_report,
    run_sync_check,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write(base: Path, rel: str, text: str) -> Path:
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


class TestSyncCheckUplift(unittest.TestCase):
    """Contract tests for manifest parity, nested site checks, historical markers, and workflows."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        for mod_name in ("test_sync_site_fixture", "test_sync_ledger_fixture"):
            sys.modules.pop(mod_name, None)
        self.tmp.cleanup()

    def test_minimal_fixture_gracefully_skips_absent_optional_manifests(self) -> None:
        _write(self.root, "pyproject.toml", '[project]\nname = "agyis-harness"\nversion = "1.1.1"\n')
        _write(self.root, "plugin.json", '{"name": "agyis-harness", "version": "1.1.1"}\n')

        report = run_sync_check(workspace_root=self.root, include_site=False)
        self.assertEqual(report["status"], "PASS", f"Unexpected mismatches: {report['mismatches']}")
        self.assertEqual(report["manifest"]["pyproject_version"], "1.1.1")
        self.assertEqual(report["manifest"]["plugin_version"], "1.1.1")
        self.assertIsNone(report["manifest"]["harness_init_version"])
        self.assertIsNone(report["manifest"]["package_json_version"])
        self.assertIsNone(report["manifest"]["uv_lock_version"])
        self.assertIsNone(report["manifest"]["og_overlay_version"])

    def test_manifest_checks_detect_drift_across_init_package_lock_and_og_svg(self) -> None:
        _write(self.root, "pyproject.toml", '[project]\nname = "agyis-harness"\nversion = "1.1.1"\n')
        _write(self.root, "plugin.json", '{"name": "agyis-harness", "version": "1.1.1"}\n')
        _write(self.root, "harness/__init__.py", '__version__ = "1.1.0"\n')
        _write(self.root, "package.json", '{"name": "agyis-harness", "version": "1.1.0"}\n')
        _write(self.root, "uv.lock", 'version = 1\n\n[[package]]\nname = "agyis-harness"\nversion = "1.1.0"\n')
        _write(self.root, "website/brand/svg/og-overlay.svg", "<svg><text>Version 1.1.0  ·  agyis-harness.io</text></svg>\n")

        report = run_sync_check(workspace_root=self.root, include_site=False)
        self.assertEqual(report["status"], "FAIL")
        joined = "\n".join(report["mismatches"])
        self.assertIn("harness/__init__.py=1.1.0", joined)
        self.assertIn("package.json=1.1.0", joined)
        self.assertIn("uv.lock=1.1.0", joined)
        self.assertIn("website/brand/svg/og-overlay.svg=1.1.0", joined)

        # Synchronize all four and confirm PASS
        _write(self.root, "harness/__init__.py", '__version__ = "1.1.1"\n')
        _write(self.root, "package.json", '{"name": "agyis-harness", "version": "1.1.1"}\n')
        _write(self.root, "uv.lock", 'version = 1\n\n[[package]]\nname = "agyis-harness"\nversion = "1.1.1"\n')
        _write(self.root, "website/brand/svg/og-overlay.svg", "<svg><text>Version 1.1.1  ·  agyis-harness.io</text></svg>\n")

        report_ok = run_sync_check(workspace_root=self.root, include_site=False)
        self.assertEqual(report_ok["status"], "PASS", f"Unexpected mismatches: {report_ok['mismatches']}")

    def test_include_site_scans_nested_routes_and_ignores_schema_and_historical_era_text(self) -> None:
        _write(self.root, "pyproject.toml", '[project]\nname = "agyis-harness"\nversion = "1.1.1"\n')
        _write(self.root, "plugin.json", '{"name": "agyis-harness", "version": "1.1.1"}\n')
        _write(
            self.root,
            "tests/test_sync_site_fixture.py",
            "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n",
        )
        _write(
            self.root,
            "website/telemetry/index.html",
            (
                "<title>Telemetry Observatory | Agyis Harness 1.1.1</title>\n"
                "<p>Corpus span: 2026-05-24 to 2026-11-25 UTC | Export schema 1.1.0 | Generated 2026-11-25T23:22:00Z</p>\n"
                "<p>Tracks harness impact across 12 release eras from Pre-Harness baseline through v1.0.0 HEAD.</p>\n"
                '<a href="https://github.com/kuasha420/agyis-harness/releases/tag/v1.1.1">Releases</a>\n'
            ),
        )
        _write(
            self.root,
            "website/cognitive/index.html",
            "<title>Cognitive Architecture | Agyis Harness 1.1.0</title>\n<p>2,572 hermetic tests</p>\n",
        )
        _write(
            self.root,
            "website/brand/index.html",
            '<p>1200 x 630 card for v1.1.0 release links.</p>\n<a href="https://github.com/kuasha420/agyis-harness/releases/tag/v1.1.0">Releases</a>\n',
        )

        report_no_site = run_sync_check(workspace_root=self.root, include_site=False)
        self.assertEqual(report_no_site["status"], "PASS")

        report_site = run_sync_check(workspace_root=self.root, include_site=True)
        self.assertEqual(report_site["status"], "FAIL")
        joined = "\n".join(report_site["mismatches"])
        self.assertIn("website/cognitive/index.html:1", joined)
        self.assertIn("website/cognitive/index.html:2", joined)
        self.assertIn("website/brand/index.html:1", joined)
        self.assertIn("website/brand/index.html:2", joined)
        self.assertNotIn("website/telemetry/index.html", joined)

    def test_historical_v1_1_marker_exempts_project_ledger_rows(self) -> None:
        _write(self.root, "pyproject.toml", '[project]\nname = "agyis-harness"\nversion = "1.1.1"\n')
        _write(self.root, "plugin.json", '{"name": "agyis-harness", "version": "1.1.1"}\n')
        _write(
            self.root,
            "tests/test_sync_ledger_fixture.py",
            "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n",
        )
        _write(
            self.root,
            "docs/taxonomy/project-ledger.md",
            (
                "# Agyis Harness Project Ledger (`v1.1.1` — Compacted)\n"
                "| **`v1.0.0` (GA Launch)** | 2026-11-25 | GA | `2,441` tests |\n"
                "| **`v1.1.0` (Uplift)** | 2026-11-27 | Uplift | `2,572` tests (`119` modules) |\n"
            ),
        )

        report = run_sync_check(workspace_root=self.root, include_site=False)
        self.assertEqual(report["status"], "PASS", f"Historical v1.1.0 row should be exempt: {report['mismatches']}")

    def test_ci_and_release_workflows_enforce_sync_check_and_changelog_section(self) -> None:
        ci_text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        rel_text = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

        self.assertIn("uv run --frozen python3 -m harness.cli audit sync-check --include-site", ci_text)
        self.assertIn("uv run --frozen python3 -m harness.cli audit sync-check --include-site", rel_text)
        self.assertIn("parse_changelog_document", rel_text)
        self.assertIn("normalize_changelog_version", rel_text)

    def test_surface_inventory_reports_32_subparsers_and_31_logical_subcommands(self) -> None:
        surface = count_surface_inventory(REPO_ROOT)
        self.assertEqual(surface["cli_subparsers"], 32)
        self.assertEqual(surface["cli_logical_subcommands"], 31)

        formatted = format_sync_check_report({
            "status": "PASS",
            "manifest": {"pyproject_version": "1.1.1", "plugin_version": "1.1.1"},
            "tool_registry": {
                "canonical": 19,
                "max_agent_tools": 20,
                "root_plan_mode": 2,
                "legacy_aliases": 9,
                "antigravity_platform_total": 30,
            },
            "surface_inventory": surface,
            "tests": {"live_tests": 2623, "live_modules": 125},
            "include_site": False,
            "mismatches": [],
        })
        self.assertIn("cli_subparsers=32 (31 logical)", formatted)


if __name__ == "__main__":
    unittest.main()
