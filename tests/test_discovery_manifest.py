# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Unit Tests for .agyis/test_manifest.json Discovery & Zero False-Pass Guards (WS2).
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from harness.cli import build_parser
from harness.commands.onboard_gates import run_onboard_verification
from harness.commands.test import cmd_test
from harness.discovery import detect_project_test_runner
from harness.discovery_manifest import (
    read_test_manifest,
    resolve_manifest_full_command,
    resolve_node_package_manager,
)


class TestDiscoveryManifestAndGuards(unittest.TestCase):
    """Hermetic tests for manifest precedence, packageManager resolution, and no-false-pass gates."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()
        self.state_dir = self.ws / ".state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._orig_state = os.environ.get("PSL_HARNESS_STATE_DIR")
        os.environ["PSL_HARNESS_STATE_DIR"] = str(self.state_dir)

    def tearDown(self) -> None:
        if self._orig_state is None:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
        else:
            os.environ["PSL_HARNESS_STATE_DIR"] = self._orig_state
        self.temp_dir.cleanup()

    def test_manifest_precedence_overrides_package_json(self) -> None:
        (self.ws / "package.json").write_text(json.dumps({"scripts": {"test": "jest"}}), encoding="utf-8")
        (self.ws / ".agyis").mkdir()
        (self.ws / ".agyis" / "test_manifest.json").write_text(
            json.dumps({
                "tiers": {"tier_2b_full": {"command": "yarn test:full", "supported": True}},
                "scripts": {"test:full": "npm run test:full"},
            }),
            encoding="utf-8",
        )
        self.assertIsNotNone(read_test_manifest(self.ws))
        self.assertEqual(resolve_manifest_full_command(self.ws), "yarn test:full")
        self.assertEqual(detect_project_test_runner(self.ws), "yarn test:full")

        # tier_3_full takes top priority when present
        (self.ws / ".agyis" / "test_manifest.json").write_text(
            json.dumps({
                "tier_3_full": "pnpm test:ci",
                "tiers": {"tier_2b_full": {"command": "yarn test:full"}},
            }),
            encoding="utf-8",
        )
        self.assertEqual(detect_project_test_runner(self.ws), "pnpm test:ci")

    def test_resolve_node_package_manager_precedence(self) -> None:
        # packageManager overrides lockfiles (mm-flextime case: package-lock.json + yarn@4.11.0)
        (self.ws / "package-lock.json").touch()
        (self.ws / "package.json").write_text(
            json.dumps({"packageManager": "yarn@4.11.0", "scripts": {"test": "vitest"}}),
            encoding="utf-8",
        )
        self.assertEqual(resolve_node_package_manager(self.ws), "yarn")
        self.assertEqual(detect_project_test_runner(self.ws), "yarn test")

        # pnpm-lock.yaml beats yarn.lock when packageManager is absent
        (self.ws / "package.json").write_text("{}", encoding="utf-8")
        (self.ws / "yarn.lock").touch()
        (self.ws / "pnpm-lock.yaml").touch()
        self.assertEqual(resolve_node_package_manager(self.ws), "pnpm")

    def test_detects_non_test_playwright_and_e2e_scripts(self) -> None:
        # mm-flextime shape: test:e2e without "test" script
        (self.ws / "package.json").write_text(
            json.dumps({
                "packageManager": "yarn@4.11.0",
                "scripts": {"test:e2e": "playwright test"},
                "devDependencies": {"@playwright/test": "^1.56.1"},
            }),
            encoding="utf-8",
        )
        self.assertEqual(detect_project_test_runner(self.ws), "yarn test:e2e")

        # @playwright/test dependency alone without scripts
        ws2 = self.ws / "pw_only"
        ws2.mkdir()
        (ws2 / "package.json").write_text(
            json.dumps({"devDependencies": {"@playwright/test": "^1.56.1"}}),
            encoding="utf-8",
        )
        self.assertEqual(detect_project_test_runner(ws2), "npx playwright test")

        # npm test:unit script
        ws3 = self.ws / "unit_only"
        ws3.mkdir()
        (ws3 / "package.json").write_text(
            json.dumps({"scripts": {"test:unit": "node --test"}}),
            encoding="utf-8",
        )
        self.assertEqual(detect_project_test_runner(ws3), "npm run test:unit")

    def test_cmd_test_and_onboard_reject_silent_unittest_false_pass_on_js_repo(self) -> None:
        # JS/Playwright files + package.json with build script only (no executable test runner)
        (self.ws / "package.json").write_text(
            json.dumps({"name": "js-no-runner", "scripts": {"build": "vite build"}}),
            encoding="utf-8",
        )
        (self.ws / "tests" / "e2e").mkdir(parents=True)
        (self.ws / "tests" / "e2e" / "i18n.spec.js").write_text("export {};\n", encoding="utf-8")

        args = build_parser("agyis").parse_args(["test", "--full", "--json"])
        out_buf = io.StringIO()
        with patch("pathlib.Path.cwd", return_value=self.ws), patch("sys.stdout", out_buf):
            code = cmd_test(args)

        self.assertEqual(code, 1)
        payload = json.loads(out_buf.getvalue())
        self.assertFalse(payload["passed"])
        self.assertEqual(payload["status"], "no_executable_runner")

        verify_res = run_onboard_verification(self.ws, dry_run=False)
        self.assertFalse(verify_res["passed"])
        self.assertEqual(verify_res["status"], "no_executable_runner")
        self.assertEqual(verify_res["exit_code"], 1)

    def test_preserves_python_unittest_fallback_and_empty_repo_skip(self) -> None:
        # Empty workspace with no manifests/tests skips cleanly in onboard verification
        empty_ws = self.ws / "empty_docs"
        empty_ws.mkdir()
        (empty_ws / "README.md").write_text("# Docs\n", encoding="utf-8")
        empty_verify = run_onboard_verification(empty_ws, dry_run=False)
        self.assertTrue(empty_verify["passed"])
        self.assertTrue(empty_verify["skipped"])
        self.assertEqual(empty_verify["reason"], "no_runner_detected")

        # Pure Python tests/test_*.py still executes unittest cleanly
        py_ws = self.ws / "py_unittest"
        (py_ws / "tests").mkdir(parents=True)
        (py_ws / "tests" / "test_ok.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self):\n        self.assertEqual(1, 1)\n",
            encoding="utf-8",
        )
        args = build_parser("agyis").parse_args(["test", "--full", "--json"])
        out_buf = io.StringIO()
        with patch("pathlib.Path.cwd", return_value=py_ws), patch("sys.stdout", out_buf):
            code = cmd_test(args)
        self.assertEqual(code, 0)
        py_payload = json.loads(out_buf.getvalue())
        self.assertTrue(py_payload["passed"])
        self.assertEqual(py_payload["tests_run"], 1)

        py_verify = run_onboard_verification(py_ws, dry_run=False)
        self.assertTrue(py_verify["passed"])
        self.assertTrue(py_verify["ran"])

    def test_cmd_test_and_onboard_consult_test_manifest_in_dry_run(self) -> None:
        (self.ws / ".agyis").mkdir()
        (self.ws / ".agyis" / "test_manifest.json").write_text(
            json.dumps({"tiers": {"tier_2b_full": {"command": "yarn test:e2e"}}}),
            encoding="utf-8",
        )
        args = build_parser("agyis").parse_args(["test", "--full", "--dry-run", "--json"])
        out_buf = io.StringIO()
        with patch("pathlib.Path.cwd", return_value=self.ws), patch("sys.stdout", out_buf):
            code = cmd_test(args)
        self.assertEqual(code, 0)
        payload = json.loads(out_buf.getvalue())
        self.assertEqual(payload["command"], "yarn test:e2e")
        self.assertTrue(payload["dry_run"])

        verify_dry = run_onboard_verification(self.ws, dry_run=True)
        self.assertTrue(verify_dry["passed"])
        self.assertEqual(verify_dry["command"], "yarn test:e2e")

    def test_cmd_test_allow_no_tests_on_empty_and_js_repos(self) -> None:
        # 1. Empty repo without tests/ fails without flag, passes cleanly with --allow-no-tests
        empty_ws = self.ws / "empty_repo"
        empty_ws.mkdir()
        (empty_ws / "README.md").write_text("# Empty\n", encoding="utf-8")

        args_fail = build_parser("agyis").parse_args(["test", "--full", "--json"])
        out_fail = io.StringIO()
        with patch("pathlib.Path.cwd", return_value=empty_ws), patch("sys.stdout", out_fail):
            self.assertEqual(cmd_test(args_fail), 1)
        self.assertEqual(json.loads(out_fail.getvalue())["status"], "no_executable_runner")

        args_allow = build_parser("agyis").parse_args(["test", "--full", "--allow-no-tests", "--json"])
        out_allow = io.StringIO()
        with patch("pathlib.Path.cwd", return_value=empty_ws), patch("sys.stdout", out_allow):
            code = cmd_test(args_allow)
        self.assertEqual(code, 0)
        payload = json.loads(out_allow.getvalue())
        self.assertTrue(payload["passed"])
        self.assertEqual(payload["tests_run"], 0)
        self.assertTrue(payload["skipped_no_tests"])
        self.assertEqual(payload["runner"], "none")
        self.assertEqual(payload["exit_code"], 0)

        # Text mode also prints skipping notice and returns 0
        args_text = build_parser("agyis").parse_args(["test", "--full", "--allow-no-tests"])
        out_text = io.StringIO()
        with patch("pathlib.Path.cwd", return_value=empty_ws), patch("sys.stdout", out_text):
            self.assertEqual(cmd_test(args_text), 0)
        self.assertIn("--allow-no-tests", out_text.getvalue())

        # 2. JS/non-Python repo with no test script passes cleanly with --allow-no-tests
        js_ws = self.ws / "js_no_test_script"
        (js_ws / "tests" / "e2e").mkdir(parents=True)
        (js_ws / "package.json").write_text(
            json.dumps({"name": "js-no-runner", "scripts": {"build": "vite build"}}),
            encoding="utf-8",
        )
        (js_ws / "tests" / "e2e" / "smoke.spec.js").write_text("export {};\n", encoding="utf-8")

        out_js = io.StringIO()
        with patch("pathlib.Path.cwd", return_value=js_ws), patch("sys.stdout", out_js):
            js_code = cmd_test(build_parser("agyis").parse_args(["test", "--full", "--allow-no-tests", "--json"]))
        self.assertEqual(js_code, 0)
        js_payload = json.loads(out_js.getvalue())
        self.assertTrue(js_payload["passed"])
        self.assertEqual(js_payload["tests_run"], 0)
        self.assertTrue(js_payload["skipped_no_tests"])
        self.assertEqual(js_payload["runner"], "none")

    def test_cmd_test_allow_no_tests_diff_affected_pkg_and_never_masks_failures(self) -> None:
        from harness.discovery import ResolvedTests

        # --diff, --affected, --pkg honor --allow-no-tests when no executable runner resolves
        js_ws = self.ws / "js_diff_no_runner"
        js_ws.mkdir()
        (js_ws / "package.json").write_text(json.dumps({"name": "no-runner"}), encoding="utf-8")

        no_runner = ResolvedTests(
            runner_cmd="",
            test_files=[],
            source_files=["packages/web/src/index.js"],
            tier=3,
            tier_name="fallback",
            scope="diff",
            package=None,
            is_empty=False,
        )
        for cli_args in (
            ["test", "--diff", "--allow-no-tests", "--json"],
            ["test", "--affected", "--allow-no-tests", "--json"],
            ["test", "--pkg", "web", "--allow-no-tests", "--json"],
        ):
            out_buf = io.StringIO()
            with patch("pathlib.Path.cwd", return_value=js_ws), \
                 patch("harness.commands.test.resolve_affected_tests", return_value=no_runner), \
                 patch("sys.stdout", out_buf):
                rc = cmd_test(build_parser("agyis").parse_args(cli_args))
            self.assertEqual(rc, 0)
            data = json.loads(out_buf.getvalue())
            self.assertTrue(data["passed"])
            self.assertEqual(data["tests_run"], 0)
            self.assertTrue(data["skipped_no_tests"])
            self.assertEqual(data["runner"], "none")

        # Fallback unittest runner on repo lacking tests/ also passes cleanly with --allow-no-tests
        empty_py_ws = self.ws / "empty_py_diff"
        empty_py_ws.mkdir()
        fallback_unittest = ResolvedTests(
            runner_cmd="python3 -m unittest discover -s tests",
            test_files=[],
            source_files=["app.py"],
            tier=3,
            tier_name="fallback",
            scope="diff",
            is_empty=False,
        )
        out_py_diff = io.StringIO()
        with patch("pathlib.Path.cwd", return_value=empty_py_ws), \
             patch("harness.commands.test.resolve_affected_tests", return_value=fallback_unittest), \
             patch("sys.stdout", out_py_diff):
            rc = cmd_test(build_parser("agyis").parse_args(["test", "--diff", "--allow-no-tests", "--json"]))
        self.assertEqual(rc, 0)
        self.assertTrue(json.loads(out_py_diff.getvalue())["skipped_no_tests"])

        # Never mask real failing test executions even with --allow-no-tests
        failing_py_ws = self.ws / "failing_py"
        (failing_py_ws / "tests").mkdir(parents=True)
        (failing_py_ws / "tests" / "test_fail.py").write_text(
            "import unittest\nclass FailCase(unittest.TestCase):\n    def test_fail(self):\n        self.fail('boom')\n",
            encoding="utf-8",
        )
        out_fail = io.StringIO()
        with patch("pathlib.Path.cwd", return_value=failing_py_ws), patch("sys.stdout", out_fail):
            fail_rc = cmd_test(build_parser("agyis").parse_args(["test", "--full", "--allow-no-tests", "--json"]))
        self.assertEqual(fail_rc, 1)
        fail_payload = json.loads(out_fail.getvalue())
        self.assertFalse(fail_payload["passed"])
        self.assertEqual(fail_payload["failures"], 1)


if __name__ == "__main__":
    unittest.main()
