# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unit and integration tests for Diff-Aware Testing & Tiered Dependency Resolver (RFC-051 Phase 2 R1 & R2).
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from harness.cli import main
from harness.discovery import (
    ResolvedTests,
    detect_project_test_runner,
    get_git_modified_files,
    inject_non_interactive_guards,
    is_git_repo,
    is_non_interactive_context,
    resolve_affected_tests,
)
from harness.hooks import completion_fence_hook


class TestGitProbing(unittest.TestCase):
    """Hermetic unit tests for git repository probing and modified file extraction."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _init_git_repo(self) -> None:
        subprocess.run(["git", "init", "-b", "main"], cwd=self.ws, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.ws, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.ws, check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=self.ws, check=True)

    def test_is_git_repo_true_and_false(self):
        self.assertFalse(is_git_repo(self.ws))
        self._init_git_repo()
        self.assertTrue(is_git_repo(self.ws))

    def test_get_git_modified_files_clean(self):
        self._init_git_repo()
        # Initial commit
        f = self.ws / "README.md"
        f.write_text("initial")
        subprocess.run(["git", "add", "README.md"], cwd=self.ws, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.ws, check=True, stdout=subprocess.DEVNULL)

        files = get_git_modified_files(self.ws)
        self.assertEqual(files, [])

    def test_get_git_modified_files_uncommitted_tracked(self):
        self._init_git_repo()
        f = self.ws / "src" / "index.py"
        f.parent.mkdir(parents=True)
        f.write_text("print('hello')\n")
        subprocess.run(["git", "add", "src/index.py"], cwd=self.ws, check=True)
        subprocess.run(["git", "commit", "-m", "add index"], cwd=self.ws, check=True, stdout=subprocess.DEVNULL)

        # Modify file unstaged
        f.write_text("print('modified')\n")
        files = get_git_modified_files(self.ws)
        self.assertEqual(files, ["src/index.py"])

    def test_get_git_modified_files_staged(self):
        self._init_git_repo()
        f = self.ws / "src" / "index.py"
        f.parent.mkdir(parents=True)
        f.write_text("v1\n")
        subprocess.run(["git", "add", "."], cwd=self.ws, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.ws, check=True, stdout=subprocess.DEVNULL)

        f.write_text("v2\n")
        subprocess.run(["git", "add", "src/index.py"], cwd=self.ws, check=True)
        files = get_git_modified_files(self.ws)
        self.assertEqual(files, ["src/index.py"])

    def test_get_git_modified_files_untracked_in_subdir(self):
        self._init_git_repo()
        f = self.ws / "README.md"
        f.write_text("init")
        subprocess.run(["git", "add", "."], cwd=self.ws, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.ws, check=True, stdout=subprocess.DEVNULL)

        # Create nested untracked file
        nested = self.ws / "nested" / "deep" / "file.ts"
        nested.parent.mkdir(parents=True)
        nested.write_text("export const x = 1;\n")

        files = get_git_modified_files(self.ws)
        self.assertEqual(files, ["nested/deep/file.ts"])

    def test_get_git_modified_files_branch_merge_base(self):
        self._init_git_repo()
        f = self.ws / "base.py"
        f.write_text("base\n")
        subprocess.run(["git", "add", "."], cwd=self.ws, check=True)
        subprocess.run(["git", "commit", "-m", "base commit"], cwd=self.ws, check=True, stdout=subprocess.DEVNULL)

        # Branch out
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=self.ws, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        feat_file = self.ws / "feat.py"
        feat_file.write_text("feature code\n")
        subprocess.run(["git", "add", "."], cwd=self.ws, check=True)
        subprocess.run(["git", "commit", "-m", "feat commit"], cwd=self.ws, check=True, stdout=subprocess.DEVNULL)

        # Diff against main branch
        files = get_git_modified_files(self.ws, branch="HEAD~1")
        self.assertIn("feat.py", files)

    def test_get_git_modified_files_exempt_binary(self):
        self._init_git_repo()
        png = self.ws / "logo.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n")
        lock = self.ws / "package-lock.json.lock"
        lock.write_text("locked")
        code = self.ws / "app.py"
        code.write_text("x = 1")

        files = get_git_modified_files(self.ws)
        self.assertEqual(files, ["app.py"])

    def test_get_git_modified_files_doc_exemptions(self):
        self._init_git_repo()
        (self.ws / "README.md").write_text("# Readme\n")
        (self.ws / "notes.txt").write_text("notes\n")
        (self.ws / "doc.rst").write_text("doc\n")
        (self.ws / "guide.markdown").write_text("guide\n")
        files = get_git_modified_files(self.ws)
        self.assertEqual(files, [])

    def test_get_git_modified_files_deleted_file(self):
        self._init_git_repo()
        f = self.ws / "old.py"
        f.write_text("old\n")
        subprocess.run(["git", "add", "."], cwd=self.ws, check=True)
        subprocess.run(["git", "commit", "-m", "add old"], cwd=self.ws, check=True, stdout=subprocess.DEVNULL)

        f.unlink()
        files = get_git_modified_files(self.ws)
        self.assertEqual(files, ["old.py"])


class TestTieredDependencyResolver(unittest.TestCase):
    """Tests 3-tier affected test dependency resolution."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_resolve_empty_diff(self):
        resolved = resolve_affected_tests(repo_root=self.ws, modified_files=[])
        self.assertTrue(resolved.is_empty)
        self.assertEqual(resolved.tier, 0)
        self.assertEqual(resolved.tier_name, "empty")
        self.assertEqual(resolved.runner_cmd, "")

    def test_resolve_level1_vitest_native(self):
        (self.ws / "vitest.config.ts").write_text("export default {};\n")
        (self.ws / "src").mkdir()
        (self.ws / "src" / "calc.ts").write_text("export const add = (a: number, b: number) => a + b;\n")

        resolved = resolve_affected_tests(
            repo_root=self.ws,
            modified_files=["src/calc.ts"],
        )
        self.assertEqual(resolved.tier, 1)
        self.assertEqual(resolved.tier_name, "native")
        self.assertIn("vitest related", resolved.runner_cmd)
        self.assertIn("src/calc.ts", resolved.runner_cmd)
        self.assertIn("--run", resolved.runner_cmd)

    def test_resolve_level1_jest_native(self):
        (self.ws / "jest.config.js").write_text("module.exports = {};\n")
        (self.ws / "src").mkdir()
        (self.ws / "src" / "calc.js").write_text("module.exports = {};\n")

        resolved = resolve_affected_tests(
            repo_root=self.ws,
            modified_files=["src/calc.js"],
        )
        self.assertEqual(resolved.tier, 1)
        self.assertEqual(resolved.tier_name, "native")
        self.assertIn("jest --findRelatedTests", resolved.runner_cmd)
        self.assertIn("src/calc.js", resolved.runner_cmd)

    def test_resolve_level2_direct_test_file(self):
        test_file = self.ws / "tests" / "test_api.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("import unittest\n")

        resolved = resolve_affected_tests(
            repo_root=self.ws,
            modified_files=["tests/test_api.py"],
        )
        self.assertEqual(resolved.tier, 2)
        self.assertEqual(resolved.tier_name, "structural")
        self.assertIn("tests/test_api.py", resolved.test_files)
        self.assertIn("tests/test_api.py", resolved.runner_cmd)

    def test_resolve_level2_deleted_test_file(self):
        # Deleted test file does not exist on disk
        resolved = resolve_affected_tests(
            repo_root=self.ws,
            modified_files=["tests/test_deleted.py"],
        )
        self.assertNotIn("tests/test_deleted.py", resolved.test_files)

    def test_resolve_level2_quoted_paths_with_spaces(self):
        test_file = self.ws / "tests" / "test space.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("import unittest\n")

        resolved = resolve_affected_tests(
            repo_root=self.ws,
            modified_files=["tests/test space.py"],
        )
        self.assertEqual(resolved.tier, 2)
        self.assertIn("'tests/test space.py'", resolved.runner_cmd)

    def test_resolve_level2_structural_co_located(self):
        src_dir = self.ws / "src"
        src_dir.mkdir(parents=True)
        btn = src_dir / "Button.tsx"
        btn.write_text("export const Button = () => null;\n")
        btn_test = src_dir / "Button.test.tsx"
        btn_test.write_text("test('btn', () => {});\n")

        resolved = resolve_affected_tests(
            repo_root=self.ws,
            modified_files=["src/Button.tsx"],
        )
        self.assertEqual(resolved.tier, 2)
        self.assertEqual(resolved.tier_name, "structural")
        self.assertIn("src/Button.test.tsx", resolved.test_files)

    def test_resolve_level2_structural_tests_dir(self):
        (self.ws / "src" / "auth").mkdir(parents=True)
        (self.ws / "src" / "auth" / "jwt.py").write_text("def verify(): pass\n")
        (self.ws / "tests" / "auth").mkdir(parents=True)
        (self.ws / "tests" / "auth" / "test_jwt.py").write_text("def test_verify(): pass\n")

        resolved = resolve_affected_tests(
            repo_root=self.ws,
            modified_files=["src/auth/jwt.py"],
        )
        self.assertEqual(resolved.tier, 2)
        self.assertEqual(resolved.tier_name, "structural")
        self.assertIn("tests/auth/test_jwt.py", resolved.test_files)

    def test_resolve_level2_python_harness_mapping(self):
        (self.ws / "harness").mkdir()
        (self.ws / "harness" / "cli.py").write_text("# cli\n")
        (self.ws / "tests").mkdir()
        (self.ws / "tests" / "test_cli.py").write_text("# test_cli\n")

        resolved = resolve_affected_tests(
            repo_root=self.ws,
            modified_files=["harness/cli.py"],
        )
        self.assertEqual(resolved.tier, 2)
        self.assertIn("tests/test_cli.py", resolved.test_files)

    def test_resolve_level3_directory_fallback(self):
        (self.ws / "src" / "auth").mkdir(parents=True)
        (self.ws / "src" / "auth" / "secret.py").write_text("# secret\n")
        (self.ws / "tests" / "auth").mkdir(parents=True)
        (self.ws / "tests" / "auth" / "test_helper.py").write_text("# test helper\n")

        resolved = resolve_affected_tests(
            repo_root=self.ws,
            modified_files=["src/auth/secret.py"],
        )
        self.assertEqual(resolved.tier, 3)
        self.assertEqual(resolved.tier_name, "fallback")
        self.assertIn("tests/auth/test_helper.py", resolved.test_files)

    def test_resolve_level3_monorepo_package_fallback(self):
        pkg_dir = self.ws / "packages" / "core"
        (pkg_dir / "src").mkdir(parents=True)
        (pkg_dir / "src" / "x.ts").write_text("export const x = 1;\n")
        (pkg_dir / "package.json").write_text(json.dumps({"name": "core", "scripts": {"test": "echo test"}}))

        resolved = resolve_affected_tests(
            repo_root=self.ws,
            modified_files=["packages/core/src/x.ts"],
        )
        self.assertEqual(resolved.tier, 3)
        self.assertEqual(resolved.tier_name, "fallback")
        self.assertEqual(resolved.package, "core")
        self.assertIn("pnpm --filter core test", resolved.runner_cmd)

    def test_resolve_affected_blast_radius(self):
        (self.ws / "src").mkdir()
        (self.ws / "src" / "lib.py").write_text("x = 1\n")
        (self.ws / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")

        resolved = resolve_affected_tests(
            repo_root=self.ws,
            modified_files=["src/lib.py"],
            mode="affected",
        )
        self.assertEqual(resolved.scope, "affected")
        self.assertTrue(len(resolved.runner_cmd) > 0)


class TestSubshellGuards(unittest.TestCase):
    """Tests non-interactive agent context detection and watch flag suppression."""

    def test_is_non_interactive_context(self):
        with patch.dict(os.environ, {"CI": "true"}):
            self.assertTrue(is_non_interactive_context())

        with patch.dict(os.environ, {"ANTIGRAVITY": "1"}):
            self.assertTrue(is_non_interactive_context())

        with patch.dict(os.environ, {"AGYIS_AGENT": "true"}):
            self.assertTrue(is_non_interactive_context())

        with patch.dict(os.environ, {"DEBIAN_FRONTEND": "noninteractive"}):
            self.assertTrue(is_non_interactive_context())

    def test_inject_guards_vitest(self):
        cmd = "vitest related src/a.ts"
        guarded_cmd, env = inject_non_interactive_guards(cmd)
        self.assertEqual(guarded_cmd, "vitest related src/a.ts --run")
        self.assertEqual(env["CI"], "true")
        self.assertEqual(env["NONINTERACTIVE"], "true")

    def test_inject_guards_jest(self):
        cmd = "jest --findRelatedTests src/a.ts"
        guarded_cmd, _ = inject_non_interactive_guards(cmd)
        self.assertEqual(guarded_cmd, "jest --findRelatedTests src/a.ts --watchAll=false")

    def test_inject_guards_pnpm_test(self):
        cmd = "pnpm test"
        guarded_cmd, _ = inject_non_interactive_guards(cmd)
        self.assertEqual(guarded_cmd, "pnpm test -- --no-watch")

        cmd2 = "pnpm test:diff"
        guarded_cmd2, _ = inject_non_interactive_guards(cmd2)
        self.assertEqual(guarded_cmd2, "pnpm test:diff -- --no-watch")

        cmd3 = "pnpm --filter my-package test"
        guarded_cmd3, _ = inject_non_interactive_guards(cmd3)
        self.assertEqual(guarded_cmd3, "pnpm --filter my-package test -- --no-watch")

    def test_inject_guards_preserves_existing(self):
        cmd_vitest = "vitest related src/a.ts --run"
        guarded_v, _ = inject_non_interactive_guards(cmd_vitest)
        self.assertEqual(guarded_v, "vitest related src/a.ts --run")

        cmd_jest = "jest --findRelatedTests src/a.ts --watchAll=false"
        guarded_j, _ = inject_non_interactive_guards(cmd_jest)
        self.assertEqual(guarded_j, "jest --findRelatedTests src/a.ts --watchAll=false")

        cmd_pnpm = "pnpm test -- --no-watch"
        guarded_p, _ = inject_non_interactive_guards(cmd_pnpm)
        self.assertEqual(guarded_p, "pnpm test -- --no-watch")


class TestCLIDiffIntegration(unittest.TestCase):
    """Tests CLI command integration for diff-aware test flags."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cli_test_diff_clean(self):
        with patch("harness.commands.test.resolve_affected_tests") as mock_resolve:
            mock_resolve.return_value = ResolvedTests(
                runner_cmd="",
                test_files=[],
                source_files=[],
                tier=0,
                tier_name="empty",
                scope="diff",
                is_empty=True,
            )
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                exit_code = main(["test", "--diff"])
            self.assertEqual(exit_code, 0)
            self.assertIn("0 affected tests detected", buf.getvalue())

    def test_cli_test_affected_clean_records_affected_tier(self):
        with patch("harness.commands.test.resolve_affected_tests") as mock_resolve, \
             patch("harness.commands.test._record_verification_all") as mock_record:
            mock_resolve.return_value = ResolvedTests(
                runner_cmd="",
                test_files=[],
                source_files=[],
                tier=0,
                tier_name="empty",
                scope="affected",
                is_empty=True,
            )
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                exit_code = main(["test", "--affected"])
            self.assertEqual(exit_code, 0)
            mock_record.assert_called_once_with(success=True, tier="affected")

    def test_cli_test_diff_executes_related(self):
        with patch("harness.commands.test.resolve_affected_tests") as mock_resolve, \
             patch("subprocess.run") as mock_run:
            mock_resolve.return_value = ResolvedTests(
                runner_cmd="python3 -m unittest tests/test_foo.py",
                test_files=["tests/test_foo.py"],
                source_files=["src/foo.py"],
                tier=2,
                tier_name="structural",
                scope="diff",
                is_empty=False,
            )
            mock_run.return_value = MagicMock(returncode=0)

            exit_code = main(["test", "--diff"])
            self.assertEqual(exit_code, 0)
            mock_run.assert_called_once()
            call_cmd = mock_run.call_args[0][0]
            self.assertIn("tests/test_foo.py", call_cmd)

    def test_cli_test_full_flag(self):
        with patch("harness.commands.test.unittest.TestLoader.discover") as mock_disc, \
             patch("harness.commands.test.unittest.TextTestRunner.run") as mock_run:
            mock_run.return_value = MagicMock(wasSuccessful=MagicMock(return_value=True))

            exit_code = main(["test", "--full"])
            self.assertEqual(exit_code, 0)
            mock_disc.assert_called_once()


if __name__ == "__main__":
    unittest.main()
