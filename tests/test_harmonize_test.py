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

    def test_audit_tauri_polyglot_multi_runner(self):
        pkg_json = self.ws / "package.json"
        pkg_json.write_text(json.dumps({
            "name": "tauri-app",
            "scripts": {"test": "vitest run"},
            "devDependencies": {"vitest": "^1.5.0"}
        }))
        (self.ws / "src-tauri").mkdir()
        (self.ws / "src-tauri" / "Cargo.toml").write_text("[package]\nname = \"src-tauri\"\n")

        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()

        # Primary runner is Node/Vitest
        self.assertEqual(audit.manifest_type, "package.json")
        self.assertEqual(audit.test_framework, "vitest")

        # Secondary runner captures Cargo in src-tauri
        self.assertEqual(len(audit.secondary_runners), 1)
        sec = audit.secondary_runners[0]
        self.assertEqual(sec["manifest_type"], "src-tauri/Cargo.toml")
        self.assertEqual(sec["test_framework"], "cargo")

        manifest = harmonizer.build_test_manifest(audit)
        self.assertIn("runners", manifest)
        self.assertIn("node", manifest["runners"])
        self.assertIn("cargo", manifest["runners"])
        self.assertIn("src-tauri/Cargo.toml", manifest["runners"]["cargo"]["manifest"])


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


class TestWS2ProbesAndManifestFidelity(unittest.TestCase):
    """WS2 tests for formatting preservation, probes, non-monorepo & manifest-only modes."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_preserves_four_space_indent_unicode_and_omits_test_pkg_on_single_pkg(self):
        pkg_json = self.ws / "package.json"
        original = (
            '{\n'
            '    "name": "café-app",\n'
            '    "description": "Résumé — 🚀",\n'
            '    "scripts": {\n'
            '        "test": "vitest run"\n'
            '    },\n'
            '    "devDependencies": {\n'
            '        "vitest": "^2.0.0"\n'
            '    }\n'
            '}\n'
        )
        pkg_json.write_text(original, encoding="utf-8")

        res = harmonize_test_runners(self.ws, dry_run=False, apply=True)
        self.assertTrue(res.success)
        updated_text = pkg_json.read_text(encoding="utf-8")
        self.assertIn('    "name": "café-app",', updated_text)
        self.assertIn('"description": "Résumé — 🚀"', updated_text)
        self.assertTrue(updated_text.endswith("\n"))
        updated = json.loads(updated_text)
        self.assertNotIn("test:pkg", updated["scripts"])

    def test_manifest_only_mode_skips_package_json_mutation(self):
        pkg_json = self.ws / "package.json"
        original = json.dumps({
            "name": "mm-flextime",
            "packageManager": "yarn@4.11.0",
            "scripts": {"test:e2e": "playwright test"},
            "devDependencies": {"@playwright/test": "^1.56.1"},
        }, indent=4) + "\n"
        pkg_json.write_text(original, encoding="utf-8")
        (self.ws / "tests" / "e2e").mkdir(parents=True)
        (self.ws / "tests" / "e2e" / "app.spec.js").write_text("test('ok', () => {});\n", encoding="utf-8")

        dry_res = harmonize_test_runners(
            self.ws, dry_run=True, apply=False, backup=False,
            mutate_package_json=False, write_manifest=False,
        )
        self.assertEqual(dry_res.mutations, [])
        self.assertFalse((self.ws / ".agyis" / "test_manifest.json").exists())
        self.assertEqual(dry_res.manifest_data["tiers"]["tier_2b_full"]["command"], "yarn test:e2e")
        self.assertTrue(dry_res.manifest_data["ui_mounting"]["vrt_pixel_diff"])

        apply_res = harmonize_test_runners(
            self.ws, dry_run=False, apply=True, backup=False,
            mutate_package_json=False, write_manifest=True,
        )
        self.assertTrue(apply_res.success)
        self.assertEqual(pkg_json.read_text(encoding="utf-8"), original)
        manifest = json.loads((self.ws / ".agyis" / "test_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["tiers"]["tier_2b_full"]["command"], "yarn test:e2e")
        self.assertEqual(manifest["package_manager"], "yarn")

    def test_playwright_and_axe_detection_and_anti_synthetic_not_applicable(self):
        (self.ws / "package.json").write_text(json.dumps({
            "name": "chess-app",
            "dependencies": {"next": "^15.0.0", "react": "^19.0.0"},
            "devDependencies": {
                "vitest": "^2.0.0",
                "@playwright/test": "^1.50.0",
                "axe-core": "^4.9.0",
                "vitest-axe": "^0.1.0",
            },
            "scripts": {"test": "vitest run"},
        }), encoding="utf-8")
        (self.ws / "playwright.config.ts").write_text("export default {};\n", encoding="utf-8")
        (self.ws / "e2e").mkdir()
        (self.ws / "e2e" / "home.spec.ts").write_text("export {};\n", encoding="utf-8")

        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()
        self.assertTrue(audit.vrt_pixel_diff)
        self.assertTrue(audit.a11y_axe)
        self.assertEqual(audit.vrt_status, "pixel_diff")
        self.assertTrue(any(r.get("test_framework") == "playwright" for r in audit.secondary_runners))
        manifest = harmonizer.build_test_manifest(audit)
        self.assertTrue(manifest["ui_mounting"]["vrt_pixel_diff"])
        self.assertTrue(manifest["ui_mounting"]["a11y_axe"])
        self.assertIn("playwright", manifest["runners"])

        # Non-frontend workspace sets anti_synthetic_score to "not_applicable"
        lib_ws = self.ws / "lib_repo"
        lib_ws.mkdir()
        (lib_ws / "package.json").write_text(json.dumps({
            "name": "pure-lib",
            "scripts": {"test": "vitest run"},
            "devDependencies": {"vitest": "^2.0.0"},
        }), encoding="utf-8")
        lib_h = TestHarmonizer(lib_ws)
        lib_manifest = lib_h.build_test_manifest(lib_h.audit())
        self.assertFalse(lib_manifest["ui_mounting"]["detected_frontend"])
        self.assertEqual(lib_manifest["ui_mounting"]["anti_synthetic_score"], "not_applicable")

    def test_nested_manifests_and_no_broken_diff_flags_on_turbo_or_node_test(self):
        from harness.harmonize.test_probes import discover_node_manifests

        (self.ws / "package.json").write_text(json.dumps({
            "name": "rn-template",
            "scripts": {"test": "npm --prefix template run test"},
        }), encoding="utf-8")
        (self.ws / "template").mkdir()
        (self.ws / "template" / "package.json").write_text(json.dumps({
            "name": "template-app",
            "scripts": {"test": "jest"},
            "devDependencies": {"jest": "^29.0.0"},
        }), encoding="utf-8")
        (self.ws / "node_modules" / "ignored_pkg").mkdir(parents=True)
        (self.ws / "node_modules" / "ignored_pkg" / "package.json").write_text("{}", encoding="utf-8")

        manifests = discover_node_manifests(self.ws)
        rel_manifests = [m.relative_to(self.ws).as_posix() for m in manifests]
        self.assertEqual(rel_manifests, ["package.json", "template/package.json"])

        res = harmonize_test_runners(self.ws, dry_run=True)
        self.assertEqual(res.audit.test_framework, "jest")
        self.assertIn("template/package.json", res.audit.nested_manifests)

        # Turbo workspace never gets -- --diff
        turbo_ws = self.ws / "turbo_repo"
        turbo_ws.mkdir()
        (turbo_ws / "turbo.json").write_text("{}", encoding="utf-8")
        (turbo_ws / "package.json").write_text(json.dumps({
            "name": "turbo-bot",
            "scripts": {"test": "turbo run test"},
            "devDependencies": {"turbo": "^2.0.0"},
        }), encoding="utf-8")
        (turbo_ws / "pnpm-lock.yaml").write_text("", encoding="utf-8")
        turbo_res = harmonize_test_runners(turbo_ws, dry_run=True)
        proposed_turbo = json.loads(turbo_res.mutations[0].proposed_content)
        self.assertEqual(proposed_turbo["scripts"]["test:diff"], "turbo run test --affected")
        self.assertNotIn("-- --diff", proposed_turbo["scripts"]["test:diff"])

        # node --test workspace never gets -- --diff / -- --affected
        node_ws = self.ws / "node_test_repo"
        node_ws.mkdir()
        (node_ws / "package.json").write_text(json.dumps({
            "name": "node-bot",
            "scripts": {"test": "node --test"},
        }), encoding="utf-8")
        node_res = harmonize_test_runners(node_ws, dry_run=True)
        proposed_node = json.loads(node_res.mutations[0].proposed_content)
        self.assertNotIn("-- --diff", proposed_node["scripts"]["test:diff"])
        self.assertNotIn("-- --affected", proposed_node["scripts"]["test:affected"])

    def test_python_caps_probe_and_cargo_uv_monorepo_detection(self):
        from harness.harmonize.test_probes import detect_python_runner_caps
        from harness.skills import is_monorepo

        cargo_ws = self.ws / "cargo_mono"
        cargo_ws.mkdir()
        (cargo_ws / "Cargo.toml").write_text('[workspace]\nmembers = ["crates/*"]\n', encoding="utf-8")
        self.assertTrue(is_monorepo(cargo_ws))

        uv_ws = self.ws / "uv_mono"
        uv_ws.mkdir()
        (uv_ws / "pyproject.toml").write_text('[tool.uv.workspace]\nmembers = ["pkgs/*"]\n', encoding="utf-8")
        self.assertTrue(is_monorepo(uv_ws))

        with patch("importlib.util.find_spec", return_value=None), patch("shutil.which", return_value=None):
            caps = detect_python_runner_caps(uv_ws)
            self.assertEqual(caps["diff_command"], "pytest")
            self.assertEqual(caps["watch_command"], "pytest")
            (uv_ws / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
            res = harmonize_test_runners(uv_ws, dry_run=True)
            self.assertEqual(res.manifest_data["tiers"]["tier_1a_diff"]["command"], "pytest")
            self.assertEqual(res.manifest_data["human_loop"]["watch_command"], "pytest")
            self.assertEqual(res.manifest_data["ui_mounting"]["anti_synthetic_score"], "not_applicable")

        # Simulated workspace .venv with pytest-picked and ptw
        (uv_ws / ".venv" / "bin").mkdir(parents=True)
        (uv_ws / ".venv" / "bin" / "ptw").write_text("#!/bin/sh\n", encoding="utf-8")
        (uv_ws / ".venv" / "lib" / "python3.14" / "site-packages" / "pytest_picked").mkdir(parents=True)
        with patch("importlib.util.find_spec", return_value=None), patch("shutil.which", return_value=None):
            caps_venv = detect_python_runner_caps(uv_ws)
            self.assertEqual(caps_venv["diff_command"], "pytest --picked")
            self.assertEqual(caps_venv["watch_command"], "ptw")

    def test_non_mutating_makefile_only_probes_actual_targets(self):
        from harness.commands.onboard_gates import run_onboard_test_manifest_sync

        makefile = self.ws / "Makefile"
        original_makefile = ".PHONY: test\ntest:\n\t@echo ok\n"
        makefile.write_text(original_makefile, encoding="utf-8")

        dry_res = harmonize_test_runners(
            self.ws,
            dry_run=True,
            apply=False,
            backup=False,
            mutate_package_json=False,
            write_manifest=False,
        )
        self.assertEqual(dry_res.mutations, [])
        self.assertEqual(dry_res.manifest_data["tiers"]["tier_2b_full"]["command"], "make test")
        self.assertEqual(dry_res.manifest_data["tiers"]["tier_1a_diff"]["command"], "make test")
        self.assertEqual(dry_res.manifest_data["tiers"]["tier_1b_affected"]["command"], "make test")
        self.assertEqual(dry_res.manifest_data["scripts"]["test:full"], "make test")
        self.assertIsNone(dry_res.manifest_data["human_loop"]["watch_command"])
        self.assertEqual(dry_res.manifest_data["runners"]["make"]["full"], "make test")
        self.assertNotIn("make test:full", json.dumps(dry_res.manifest_data))

        apply_res = harmonize_test_runners(
            self.ws,
            dry_run=False,
            apply=True,
            backup=False,
            mutate_package_json=False,
            write_manifest=True,
        )
        self.assertEqual(apply_res.mutations, [])
        self.assertEqual(makefile.read_text(encoding="utf-8"), original_makefile)
        manifest_written = json.loads((self.ws / ".agyis" / "test_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest_written["tiers"]["tier_2b_full"]["command"], "make test")

        sync_res = run_onboard_test_manifest_sync(self.ws, dry_run=False)
        self.assertTrue(sync_res["generated"])
        self.assertEqual(sync_res["tiers"]["tier_2b_full"]["command"], "make test")
        self.assertEqual(makefile.read_text(encoding="utf-8"), original_makefile)

        # Fallback to `make check` when `test:` is absent and `check:` is present
        check_ws = self.ws / "check_only"
        check_ws.mkdir()
        (check_ws / "Makefile").write_text("check:\n\t@echo checking\n", encoding="utf-8")
        check_res = harmonize_test_runners(
            check_ws, dry_run=True, mutate_package_json=False, write_manifest=False
        )
        self.assertEqual(check_res.manifest_data["tiers"]["tier_2b_full"]["command"], "make check")
        self.assertEqual(check_res.manifest_data["tiers"]["tier_1a_diff"]["command"], "make check")
        self.assertEqual(check_res.manifest_data["tiers"]["tier_1b_affected"]["command"], "make check")

        # Explicit `test:diff:` is honored while missing `test:full:` still falls back to `make test`
        partial_ws = self.ws / "partial_targets"
        partial_ws.mkdir()
        (partial_ws / "Makefile").write_text("test:\n\t@echo all\ntest:diff:\n\t@echo diff\n", encoding="utf-8")
        partial_res = harmonize_test_runners(
            partial_ws, dry_run=True, mutate_package_json=False, write_manifest=False
        )
        self.assertEqual(partial_res.manifest_data["tiers"]["tier_1a_diff"]["command"], "make test:diff")
        self.assertEqual(partial_res.manifest_data["tiers"]["tier_1b_affected"]["command"], "make test:diff")
        self.assertEqual(partial_res.manifest_data["tiers"]["tier_2b_full"]["command"], "make test")


if __name__ == "__main__":
    unittest.main()
