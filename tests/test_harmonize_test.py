# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Unit & Integration Tests for Test Runner Harmonization Engine (RFC-051 Phase 2).
Covers:
- TestAuditManifests (Node, Rust, Python, Makefile, monorepo)
- TestScriptPreservation (custom scripts never overwritten)
- TestSafeDualMode (zero mutation on dry-run, applied on --apply/--yes)
- TestBackupPatch (unified diff patch created in .agyis/backups/)
- TestUIMountingUpgrades (happy-dom/jsdom detection, missing DOM env flagging)
- TestManifestGeneration (.agyis/test_manifest.json schema compliance)
- TestCLIIntegration (CLI entrypoints for harmonize test and test --harmonize)
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from harness.cli import main
from harness.harmonize.test_runner import (
    HarmonizeTestResult,
    TestAuditReport,
    TestHarmonizer,
    harmonize_test_runners,
)


class TestAuditManifests(unittest.TestCase):
    """Hermetic unit tests for workspace test manifest auditing."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_audit_node_vitest(self):
        pkg_json = self.ws / "package.json"
        pkg_json.write_text(json.dumps({
            "name": "sample-node-vitest",
            "scripts": {
                "test": "vitest run"
            },
            "devDependencies": {
                "vitest": "^1.5.0"
            }
        }))

        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()

        self.assertEqual(audit.manifest_type, "package.json")
        self.assertEqual(audit.test_framework, "vitest")
        self.assertEqual(audit.package_manager, "npm")
        self.assertIn("test:diff", audit.missing_scripts)
        self.assertIn("test:affected", audit.missing_scripts)

    def test_audit_node_jest_pnpm(self):
        pkg_json = self.ws / "package.json"
        pkg_json.write_text(json.dumps({
            "name": "sample-node-jest",
            "scripts": {
                "test": "jest"
            },
            "devDependencies": {
                "jest": "^29.0.0"
            }
        }))
        (self.ws / "pnpm-lock.yaml").write_text("lockfileVersion: 5.4")

        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()

        self.assertEqual(audit.manifest_type, "package.json")
        self.assertEqual(audit.test_framework, "jest")
        self.assertEqual(audit.package_manager, "pnpm")

    def test_audit_rust_cargo(self):
        cargo_toml = self.ws / "Cargo.toml"
        cargo_toml.write_text("[package]\nname = \"sample-rust\"\nversion = \"0.1.0\"\n")

        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()

        self.assertEqual(audit.manifest_type, "Cargo.toml")
        self.assertEqual(audit.test_framework, "cargo")
        self.assertEqual(audit.package_manager, "cargo")

    def test_audit_python_pyproject(self):
        pyproj = self.ws / "pyproject.toml"
        pyproj.write_text("[tool.pytest.ini_options]\nminversion = \"6.0\"\n")

        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()

        self.assertEqual(audit.manifest_type, "pyproject.toml")
        self.assertEqual(audit.test_framework, "pytest")
        self.assertEqual(audit.package_manager, "pip")

    def test_audit_makefile(self):
        make_file = self.ws / "Makefile"
        make_file.write_text("test:\n\t@echo 'running tests'\n")

        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()

        self.assertEqual(audit.manifest_type, "Makefile")
        self.assertEqual(audit.test_framework, "make")


class TestScriptPreservation(unittest.TestCase):
    """Ensures existing custom scripts are never overwritten."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_preserve_custom_test_diff_script(self):
        pkg_json = self.ws / "package.json"
        pkg_json.write_text(json.dumps({
            "name": "sample-custom-scripts",
            "scripts": {
                "test:diff": "my-custom-test-diff-runner --custom-flag",
                "test": "vitest"
            },
            "devDependencies": {
                "vitest": "^1.0.0"
            }
        }, indent=2))

        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()

        self.assertIn("test:diff", audit.preserved_custom_scripts)
        self.assertEqual(audit.existing_scripts["test:diff"], "my-custom-test-diff-runner --custom-flag")

        mutations = harmonizer.plan_mutations(audit)
        self.assertEqual(len(mutations), 1)
        proposed_data = json.loads(mutations[0].proposed_content)
        # Verify custom script was preserved exactly
        self.assertEqual(proposed_data["scripts"]["test:diff"], "my-custom-test-diff-runner --custom-flag")
        # Verify missing scripts were injected
        self.assertEqual(proposed_data["scripts"]["test:affected"], "vitest related --run")


class TestSafeDualMode(unittest.TestCase):
    """Tests dry-run vs apply modes and safe mutation contracts."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_dry_run_zero_mutation(self):
        pkg_json = self.ws / "package.json"
        original_content = json.dumps({
            "name": "sample-dry-run",
            "scripts": {
                "test": "vitest"
            },
            "devDependencies": {
                "vitest": "^1.0.0"
            }
        }, indent=2)
        pkg_json.write_text(original_content)

        res = harmonize_test_runners(self.ws, dry_run=True, apply=False)

        self.assertTrue(res.success)
        self.assertTrue(res.dry_run)
        self.assertFalse(res.applied)
        # Disk content unchanged
        self.assertEqual(pkg_json.read_text(), original_content)
        # Manifest not written to disk in dry-run
        self.assertFalse((self.ws / ".agyis" / "test_manifest.json").exists())
        # Unified diff is previewed
        self.assertTrue(len(res.mutations) > 0)
        self.assertIn("+    \"test:diff\"", res.mutations[0].unified_diff)

    def test_apply_mode_writes_changes_and_manifest(self):
        pkg_json = self.ws / "package.json"
        pkg_json.write_text(json.dumps({
            "name": "sample-apply",
            "scripts": {
                "test": "vitest"
            },
            "devDependencies": {
                "vitest": "^1.0.0"
            }
        }, indent=2))

        res = harmonize_test_runners(self.ws, dry_run=False, apply=True)

        self.assertTrue(res.success)
        self.assertFalse(res.dry_run)
        self.assertTrue(res.applied)
        # Disk content updated
        updated_data = json.loads(pkg_json.read_text())
        self.assertIn("test:diff", updated_data["scripts"])
        self.assertEqual(updated_data["scripts"]["test:diff"], "vitest related --run")
        # Manifest created on disk
        manifest_file = self.ws / ".agyis" / "test_manifest.json"
        self.assertTrue(manifest_file.exists())


class TestBackupPatch(unittest.TestCase):
    """Ensures pre-mutation unified diff backup patch is created."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_backup_patch_created_on_apply(self):
        pkg_json = self.ws / "package.json"
        pkg_json.write_text(json.dumps({
            "name": "sample-patch",
            "scripts": {
                "test": "vitest"
            },
            "devDependencies": {
                "vitest": "^1.0.0"
            }
        }, indent=2))

        res = harmonize_test_runners(self.ws, dry_run=False, apply=True)

        self.assertIsNotNone(res.backup_patch)
        self.assertTrue(res.backup_patch.is_file())
        patch_text = res.backup_patch.read_text()
        self.assertIn("--- a/package.json", patch_text)
        self.assertIn("+++ b/package.json", patch_text)
        self.assertIn("+    \"test:diff\": \"vitest related --run\"", patch_text)


class TestUIMountingUpgrades(unittest.TestCase):
    """Tests DOM mounting environment audit and recommendations."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_dom_env_detected(self):
        pkg_json = self.ws / "package.json"
        pkg_json.write_text(json.dumps({
            "name": "sample-ui-project",
            "dependencies": {
                "react": "^18.2.0"
            },
            "devDependencies": {
                "vitest": "^1.0.0"
            }
        }))
        vitest_cfg = self.ws / "vitest.config.ts"
        vitest_cfg.write_text("import { defineConfig } from 'vitest/config';\nexport default defineConfig({});\n")

        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()

        self.assertEqual(audit.ui_mounting_status, "missing_dom_env")
        self.assertTrue(any("happy-dom" in gap for gap in audit.gaps))

    def test_optimal_dom_env_detected(self):
        pkg_json = self.ws / "package.json"
        pkg_json.write_text(json.dumps({
            "name": "sample-ui-project",
            "dependencies": {
                "react": "^18.2.0"
            },
            "devDependencies": {
                "vitest": "^1.0.0",
                "happy-dom": "^14.0.0"
            }
        }))
        vitest_cfg = self.ws / "vitest.config.ts"
        vitest_cfg.write_text("import { defineConfig } from 'vitest/config';\nexport default defineConfig({ test: { environment: 'happy-dom' } });\n")

        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()

        self.assertEqual(audit.ui_mounting_status, "optimal")


class TestManifestGeneration(unittest.TestCase):
    """Validates .agyis/test_manifest.json schema and tier metadata."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_manifest_schema_compliance(self):
        pkg_json = self.ws / "package.json"
        pkg_json.write_text(json.dumps({
            "name": "sample-manifest",
            "scripts": {
                "test": "vitest"
            },
            "devDependencies": {
                "vitest": "^1.0.0"
            }
        }))

        res = harmonize_test_runners(self.ws, dry_run=False, apply=True)
        manifest_file = self.ws / ".agyis" / "test_manifest.json"
        data = json.loads(manifest_file.read_text())

        self.assertEqual(data["version"], "1.0.0")
        self.assertEqual(data["framework"], "vitest")
        self.assertEqual(data["package_manager"], "npm")
        self.assertIn("tier_1a_diff", data["tiers"])
        self.assertIn("tier_1b_affected", data["tiers"])
        self.assertIn("tier_2a_pkg", data["tiers"])
        self.assertIn("tier_2b_full", data["tiers"])
        self.assertTrue(data["tiers"]["tier_1a_diff"]["clears_turn_code_dirty"])
        self.assertTrue(data["tiers"]["tier_1b_affected"]["required_for_handoff"])
        self.assertTrue(data["tiers"]["tier_2b_full"]["required_for_commit"])

    def test_manifest_cargo_commands(self):
        (self.ws / "Cargo.toml").write_text("[package]\nname = 'my-rust-crate'\nversion = '0.1.0'\n")
        res = harmonize_test_runners(self.ws, dry_run=False, apply=True)
        manifest_file = self.ws / ".agyis" / "test_manifest.json"
        data = json.loads(manifest_file.read_text())

        self.assertEqual(data["framework"], "cargo")
        self.assertEqual(data["package_manager"], "cargo")
        self.assertEqual(data["tiers"]["tier_1a_diff"]["command"], "cargo test")
        self.assertEqual(data["tiers"]["tier_1b_affected"]["command"], "cargo test")
        self.assertEqual(data["tiers"]["tier_2b_full"]["command"], "cargo test")
        self.assertEqual(data["human_loop"]["watch_command"], "cargo watch -x test")

    def test_manifest_makefile_commands(self):
        (self.ws / "Makefile").write_text("all:\n\techo ok\n")
        res = harmonize_test_runners(self.ws, dry_run=False, apply=True)
        manifest_file = self.ws / ".agyis" / "test_manifest.json"
        data = json.loads(manifest_file.read_text())

        self.assertEqual(data["framework"], "make")
        self.assertEqual(data["tiers"]["tier_1a_diff"]["command"], "make test:diff")
        self.assertEqual(data["tiers"]["tier_1b_affected"]["command"], "make test:affected")
        self.assertEqual(data["tiers"]["tier_2b_full"]["command"], "make test:full")
        self.assertEqual(data["human_loop"]["watch_command"], "make test:watch")


class TestCLIIntegration(unittest.TestCase):
    """Tests CLI entrypoints for test runner harmonization."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cli_harmonize_test_dry_run(self):
        pkg_json = self.ws / "package.json"
        pkg_json.write_text(json.dumps({
            "name": "sample-cli-dry-run",
            "scripts": {
                "test": "jest"
            },
            "devDependencies": {
                "jest": "^29.0.0"
            }
        }))

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            code = main(["harmonize", "test", str(self.ws), "--dry-run"])

        self.assertEqual(code, 0)
        output = stdout_buf.getvalue()
        self.assertIn("[DRY-RUN]", output)
        self.assertIn("Framework: jest (npm)", output)

    def test_cli_harmonize_test_apply_json(self):
        pkg_json = self.ws / "package.json"
        pkg_json.write_text(json.dumps({
            "name": "sample-cli-apply",
            "scripts": {
                "test": "vitest"
            },
            "devDependencies": {
                "vitest": "^1.0.0"
            }
        }))

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            code = main(["harmonize", "test", str(self.ws), "--apply", "--json"])

        self.assertEqual(code, 0)
        data = json.loads(stdout_buf.getvalue())
        self.assertTrue(data["applied"])
        self.assertFalse(data["dry_run"])
        self.assertEqual(data["audit"]["test_framework"], "vitest")

    def test_cli_test_flag_harmonize_dry_run(self):
        pkg_json = self.ws / "package.json"
        pkg_json.write_text(json.dumps({
            "name": "sample-cli-test-flag",
            "scripts": {
                "test": "vitest"
            },
            "devDependencies": {
                "vitest": "^1.0.0"
            }
        }))

        stdout_buf = io.StringIO()
        with patch("pathlib.Path.cwd", return_value=self.ws):
            with patch("sys.stdout", stdout_buf):
                code = main(["test", "--harmonize", "--dry-run"])

        self.assertEqual(code, 0)
        self.assertIn("[DRY-RUN]", stdout_buf.getvalue())


if __name__ == "__main__":
    unittest.main()
