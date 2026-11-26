#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Wave 1.1 tests for CLI parity (re/ext --help, clean --caches, test --json,
rules --lint --dedup, skills AGYIS_CONFIG_DIR), onboard contracts (--rea, --verify,
--no-verify, --commit, untracked warning), and packaged uv launcher shim preservation.
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
from unittest.mock import patch

from harness.cli import main as cli_main
from harness.commands.onboard import cmd_onboard
from harness.delivery.bin_launcher import _resolve_launcher_python, install_launchers


class TestCliParityAndLaunchers(unittest.TestCase):
    """Tests CLI help forwarding, clean --caches, test --json, rules --lint --dedup, skills env, and bin_launcher."""

    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.ws = Path(self.td.name).resolve()

    def tearDown(self) -> None:
        self.td.cleanup()

    def test_re_and_ext_help_forwarding(self) -> None:
        for cmd_name in ("re", "ext"):
            with patch("sys.stdout", new_callable=io.StringIO) as out_buf:
                with self.assertRaises(SystemExit) as ctx:
                    cli_main([cmd_name, "--help"], prog="agyis")
                self.assertEqual(ctx.exception.code, 0)
                self.assertIn(f"agyis {cmd_name}", out_buf.getvalue())

    def test_clean_caches_dry_run_and_live(self) -> None:
        for rel in (".next", ".turbo", "node_modules/.cache"):
            d = self.ws / rel
            d.mkdir(parents=True, exist_ok=True)
            (d / "artifact.tmp").write_text("stale", encoding="utf-8")

        with patch("sys.stdout", new_callable=io.StringIO) as out_dry:
            code_dry = cli_main(["clean", "-w", str(self.ws), "--caches", "--dry-run", "--json"], prog="agyis")
            self.assertEqual(code_dry, 0)
            data_dry = json.loads(out_dry.getvalue())
            self.assertEqual(data_dry["caches"]["count"], 3)
            self.assertTrue((self.ws / ".next").exists())

        with patch("sys.stdout", new_callable=io.StringIO) as out_live:
            code_live = cli_main(["clean", "-w", str(self.ws), "--caches", "--json"], prog="agyis")
            self.assertEqual(code_live, 0)
            data_live = json.loads(out_live.getvalue())
            self.assertEqual(data_live["caches"]["count"], 3)
            self.assertFalse((self.ws / ".next").exists())
            self.assertFalse((self.ws / ".turbo").exists())

    def test_cmd_test_json_across_modes(self) -> None:
        test_dir = self.ws / "sample_tests"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "test_mini.py").write_text(
            "import unittest\nclass M(unittest.TestCase):\n    def test_ok(self):\n        self.assertEqual(1, 1)\n",
            encoding="utf-8",
        )
        orig_cwd = os.getcwd()
        os.chdir(self.ws)
        try:
            with patch("sys.stdout", new_callable=io.StringIO) as out_buf, \
                 patch("harness.commands.test._record_verification_all"):
                code = cli_main(["test", "-s", str(test_dir), "--json"], prog="agyis")
                self.assertEqual(code, 0)
                payload = json.loads(out_buf.getvalue())
                self.assertTrue(payload["passed"])
                self.assertEqual(payload["mode"], "unittest")
                self.assertEqual(payload["tests_run"], 1)

            subprocess.run(["git", "init", "-b", "main"], cwd=self.ws, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.name", "T"], cwd=self.ws, check=True)
            subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=self.ws, check=True)
            subprocess.run(["git", "add", "."], cwd=self.ws, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=self.ws, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with patch("sys.stdout", new_callable=io.StringIO) as diff_buf, \
                 patch("harness.commands.test._record_verification_all"):
                code_diff = cli_main(["test", "--diff", "--json"], prog="agyis")
                self.assertEqual(code_diff, 0)
                diff_data = json.loads(diff_buf.getvalue())
                self.assertTrue(diff_data["passed"])
                self.assertEqual(diff_data["mode"], "diff")
        finally:
            os.chdir(orig_cwd)

    def test_rules_lint_and_dedup_combined_and_skills_env(self) -> None:
        # 1. rules --lint --dedup in a single invocation
        fake_dedup = {"pruned_files": [str(self.ws / "AGENTS.md")], "tokens_saved": 12, "chars_removed": 48, "removed_sections": ["dup"]}
        fake_lint = {"workspace": str(self.ws), "clean": True, "files_scanned": 2, "echoes": []}
        with patch("harness.commands.rules.enforce_single_source_rules", return_value=fake_dedup) as mock_d, \
             patch("harness.commands.rules.lint_rule_echo", return_value=fake_lint) as mock_l, \
             patch("sys.stdout", new_callable=io.StringIO) as out_buf:
            code = cli_main(["rules", "-w", str(self.ws), "--lint", "--dedup", "--json"], prog="agyis")
            self.assertEqual(code, 0)
            mock_d.assert_called_once()
            mock_l.assert_called_once()
            data = json.loads(out_buf.getvalue())
            self.assertIn("lint", data)
            self.assertIn("dedup", data)
            self.assertTrue(data["clean"])

        # 2. skills --prune-duplicates honors AGYIS_CONFIG_DIR
        cfg_dir = self.ws / "custom_cfg"
        (cfg_dir / "plugins" / "p1" / "skills" / "my-skill").mkdir(parents=True, exist_ok=True)
        (cfg_dir / "plugins" / "p1" / "skills" / "my-skill" / "SKILL.md").write_text("# S\n", encoding="utf-8")
        ws_skill = self.ws / ".agents" / "skills" / "my-skill"
        ws_skill.mkdir(parents=True, exist_ok=True)
        (ws_skill / "SKILL.md").write_text("# Duplicate\n", encoding="utf-8")
        with patch.dict(os.environ, {"AGYIS_CONFIG_DIR": str(cfg_dir)}), \
             patch("sys.stdout", new_callable=io.StringIO) as sk_out:
            code_sk = cli_main(["skills", "--prune-duplicates", "-w", str(self.ws), "--json"], prog="agyis")
            self.assertEqual(code_sk, 0)
            sk_data = json.loads(sk_out.getvalue())
            self.assertEqual(sk_data["total_pruned"], 1)
            self.assertFalse(ws_skill.exists())

    def test_bin_launcher_preserves_uv_or_packaged_python(self) -> None:
        bin_dir = self.ws / "bin"
        target_dir = self.ws / "plugin"
        source_dir = self.ws / "site-packages"
        target_dir.mkdir()
        source_dir.mkdir()
        fake_uv_py = "/home/testuser/.local/share/uv/tools/agyis-harness/bin/python3"

        with patch("harness.delivery.bin_launcher.is_packaged_wheel_install", return_value=True), \
             patch.object(sys, "prefix", "/home/testuser/.local/share/uv/tools/agyis-harness"), \
             patch.object(sys, "base_prefix", "/usr"), \
             patch.object(sys, "executable", fake_uv_py):
            resolved = _resolve_launcher_python(source_dir)
            self.assertEqual(resolved, fake_uv_py)
            agyis_bin, _ = install_launchers(bin_dir, [], source_dir, target_dir)
            txt = agyis_bin.read_text(encoding="utf-8")
            self.assertTrue(txt.startswith(f"#!{fake_uv_py}\n"))
            self.assertIn("_AGYIS_LAUNCHER_REEXEC", txt)
            self.assertIn("os.environ.pop('_AGYIS_LAUNCHER_REEXEC', None)", txt)
            self.assertIn("os.path.abspath(sys.executable)", txt)
            self.assertNotIn("#!/usr/bin/env python3\n", txt)

        # Source checkout launcher also uses abspath + reexec loop guard & cleanup
        with patch("harness.delivery.bin_launcher.is_packaged_wheel_install", return_value=False):
            checkout_dir = self.ws / "repo_src"
            checkout_dir.mkdir()
            agyis_src_bin, _ = install_launchers(self.ws / "bin_src", [], checkout_dir, target_dir)
            src_txt = agyis_src_bin.read_text(encoding="utf-8")
            self.assertIn("os.path.abspath(sys.executable) != target_py_abs", src_txt)
            self.assertIn("os.environ.pop('_AGYIS_LAUNCHER_REEXEC', None)", src_txt)


class TestOnboardWave1Contracts(unittest.TestCase):
    """Tests onboard --rea, --verify, --no-verify, --commit, and untracked safety warnings."""

    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.ws = Path(self.td.name).resolve()
        self.cfg = self.ws / "cfg"
        self.cfg.mkdir(parents=True, exist_ok=True)
        self.repo = self.ws / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=self.repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=self.repo, check=True)
        (self.repo / "README.md").write_text("# Demo\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def tearDown(self) -> None:
        self.td.cleanup()

    def test_onboard_rea_and_atomic_commit_with_untracked_warning(self) -> None:
        # Leave tracked README dirty AND create untracked file
        (self.repo / "README.md").write_text("# Dirty\n", encoding="utf-8")
        (self.repo / "stray_untracked.txt").write_text("note\n", encoding="utf-8")

        with patch("harness.runtime.healing.provision_rea_skill") as mock_prov, \
             patch("sys.stdout", new_callable=io.StringIO) as out_buf, \
             patch("sys.stderr", new_callable=io.StringIO) as err_buf:
            code = cmd_onboard(
                self.repo,
                allow_dirty=True,
                commit=True,
                rea=True,
                json_output=True,
                config_dir=self.cfg,
            )
        self.assertEqual(code, 0)
        self.assertIn("untracked", err_buf.getvalue().lower())
        data = json.loads(out_buf.getvalue())
        self.assertTrue(data["rea"])
        self.assertTrue(data["experimental_rea"])
        self.assertTrue(data["committed"])
        self.assertIsNotNone(data["untracked_warning"])
        mock_prov.assert_called_once()
        cfg_data = json.loads((self.repo / ".agyis" / "config.json").read_text(encoding="utf-8"))
        self.assertTrue(cfg_data["rea"])
        self.assertTrue((self.repo / ".agents" / "ledger").is_dir())
        # Verify atomic commit includes tracked AGENTS.md (not .agyis/config.json, excluded via .git/info/exclude, nor dirty README.md)
        show_files = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=self.repo, capture_output=True, text=True, check=True).stdout
        self.assertIn("AGENTS.md", show_files)
        self.assertNotIn(".agyis/config.json", show_files)
        self.assertNotIn("README.md", show_files)

    def test_onboard_detected_runner_and_verify_no_verify_precedence(self) -> None:
        # 1. Authentic detected runner path (package.json -> npm test via inject_non_interactive_guards)
        shim_bin = self.ws / "shim_bin"
        shim_bin.mkdir()
        receipt = self.ws / "npm_receipt.txt"
        npm_shim = shim_bin / "npm"
        npm_shim.write_text(
            f"#!/bin/sh\nprintf '%s|%s\\n' \"$*\" \"$CI\" > '{receipt}'\n",
            encoding="utf-8",
        )
        npm_shim.chmod(0o755)
        (self.repo / "package.json").write_text(json.dumps({"name": "demo", "scripts": {"test": "echo ok"}}), encoding="utf-8")
        subprocess.run(["git", "add", "package.json"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-m", "add package.json"], cwd=self.repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        with patch.dict(os.environ, {"PATH": f"{shim_bin}{os.pathsep}{os.environ.get('PATH', '')}"}), \
             patch("sys.stdout", new_callable=io.StringIO) as out_pkg:
            code_pkg = cmd_onboard(self.repo, verify=True, json_output=True, config_dir=self.cfg)
        self.assertEqual(code_pkg, 0)
        pkg_data = json.loads(out_pkg.getvalue())
        self.assertTrue(pkg_data["verification"]["ran"])
        self.assertTrue(pkg_data["verification"]["passed"])
        self.assertEqual(pkg_data["verification"]["command"], "npm test")
        self.assertEqual(receipt.read_text(encoding="utf-8").strip(), "test -- --no-watch|true")

        # 2. Explicit --verify --no-verify combination suppresses failing verification
        (self.repo / "package.json").unlink()
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-m", "drop package.json"], cwd=self.repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tdir = self.repo / "tests"
        tdir.mkdir()
        (tdir / "test_fail.py").write_text(
            "import unittest\nclass F(unittest.TestCase):\n    def test_bad(self):\n        self.fail('boom')\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "tests/test_fail.py"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-m", "add failing test"], cwd=self.repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        with patch("sys.stdout", new_callable=io.StringIO) as out_nov:
            code_nov = cmd_onboard(self.repo, verify=True, no_verify=True, json_output=True, config_dir=self.cfg)
        self.assertEqual(code_nov, 0)
        nov_data = json.loads(out_nov.getvalue())
        self.assertIsNone(nov_data["verification"])

    def test_onboard_verify_failure_aborts_and_no_verify_skips(self) -> None:
        tdir = self.repo / "tests"
        tdir.mkdir()
        (tdir / "test_fail.py").write_text(
            "import unittest\nclass F(unittest.TestCase):\n    def test_bad(self):\n        self.fail('boom')\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "tests/test_fail.py"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-m", "add failing test"], cwd=self.repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        with patch("sys.stdout", new_callable=io.StringIO) as out_fail:
            code_fail = cmd_onboard(self.repo, verify=True, commit=True, json_output=True, config_dir=self.cfg)
        self.assertEqual(code_fail, 1)
        data_fail = json.loads(out_fail.getvalue())
        self.assertFalse(data_fail["success"])
        self.assertFalse(data_fail["verification"]["passed"])

        # Commit/clean worktree from aborted attempt isn't created, and --pr --no-verify bypasses verification
        real_run = subprocess.run

        def _mock_push(cmd, *args, **kwargs):
            if cmd and cmd[0] == "git" and len(cmd) > 1 and cmd[1] == "push":
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return real_run(cmd, *args, **kwargs)

        with patch("harness.commands.onboard.create_pull_request", return_value=(True, "https://github.com/o/r/pull/1")), \
             patch("subprocess.run", side_effect=_mock_push), \
             patch("sys.stdout", new_callable=io.StringIO) as out_ok, \
             patch("sys.stderr", new_callable=io.StringIO):
            code_ok = cmd_onboard(
                self.repo,
                allow_dirty=True,
                open_pr=True,
                no_verify=True,
                json_output=True,
                config_dir=self.cfg,
            )
        self.assertEqual(code_ok, 0)
        data_ok = json.loads(out_ok.getvalue())
        self.assertTrue(data_ok["success"])
        self.assertTrue(data_ok["committed"])
        self.assertTrue(data_ok["pr_opened"])


if __name__ == "__main__":
    unittest.main()
