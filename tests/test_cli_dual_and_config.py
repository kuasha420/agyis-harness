#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unit and integration tests for harness/cli.py
"""

import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from harness.cli import main

DYNAMIC_TEST_MODULES = (
    "test_sample",
    "test_clear_state_sample",
    "test_dual_cli_sample",
)


class TestAgyisPathAndConfigHierarchy(unittest.TestCase):
    """Hermetic unit tests for AGYIS_* and PSL_* path and config fallback hierarchies."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_config_and_data_dir_hierarchy(self) -> None:
        from harness.telemetry.config import get_config_dir, get_data_dir
        agyis_cfg = self.base / "agyis_cfg"
        psl_cfg = self.base / "psl_cfg"

        # AGYIS_CONFIG_DIR takes precedence
        with patch.dict(os.environ, {"AGYIS_CONFIG_DIR": str(agyis_cfg), "PSL_CONFIG_DIR": str(psl_cfg)}, clear=False):
            self.assertEqual(get_config_dir(), agyis_cfg.resolve())

        # PSL_CONFIG_DIR honored when AGYIS_CONFIG_DIR is unset
        with patch.dict(os.environ, {"PSL_CONFIG_DIR": str(psl_cfg)}, clear=False):
            os.environ.pop("AGYIS_CONFIG_DIR", None)
            os.environ.pop("AGYIS_HARNESS_STATE_DIR", None)
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
            self.assertEqual(get_config_dir(), psl_cfg.resolve())

        # Data dir precedence
        agyis_data = self.base / "agyis_data"
        psl_data = self.base / "psl_data"
        with patch.dict(os.environ, {"AGYIS_DATA_DIR": str(agyis_data), "PSL_DATA_DIR": str(psl_data)}, clear=False):
            self.assertEqual(get_data_dir(), agyis_data.resolve())

        with patch.dict(os.environ, {"PSL_DATA_DIR": str(psl_data)}, clear=False):
            os.environ.pop("AGYIS_DATA_DIR", None)
            os.environ.pop("AGYIS_HARNESS_STATE_DIR", None)
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
            self.assertEqual(get_data_dir(), psl_data.resolve())

    def test_state_dir_hierarchy(self) -> None:
        from harness.utils.state import get_state_dir
        agyis_state = self.base / "agyis_state"
        psl_state = self.base / "psl_state"

        with patch.dict(os.environ, {"AGYIS_HARNESS_STATE_DIR": str(agyis_state), "PSL_HARNESS_STATE_DIR": str(psl_state)}, clear=False):
            self.assertEqual(get_state_dir(), agyis_state)

        with patch.dict(os.environ, {"PSL_HARNESS_STATE_DIR": str(psl_state)}, clear=False):
            os.environ.pop("AGYIS_HARNESS_STATE_DIR", None)
            self.assertEqual(get_state_dir(), psl_state)

    def test_auth_token_and_sync_endpoint_hierarchy(self) -> None:
        from harness.telemetry.config import get_auth_token, get_sync_endpoint

        with patch.dict(os.environ, {"AGYIS_AUTH_TOKEN": "agyis-tok", "PSL_AUTH_TOKEN": "psl-tok"}, clear=False):
            self.assertEqual(get_auth_token(), "agyis-tok")

        with patch.dict(os.environ, {"PSL_AUTH_TOKEN": "psl-tok"}, clear=False):
            os.environ.pop("AGYIS_AUTH_TOKEN", None)
            self.assertEqual(get_auth_token(), "psl-tok")

        with patch.dict(os.environ, {"AGYIS_SYNC_ENDPOINT": "https://agyis.hub", "PSL_SYNC_ENDPOINT": "https://psl.hub"}, clear=False):
            self.assertEqual(get_sync_endpoint(), "https://agyis.hub")

        with patch.dict(os.environ, {"PSL_SYNC_ENDPOINT": "https://psl.hub"}, clear=False):
            os.environ.pop("AGYIS_SYNC_ENDPOINT", None)
            self.assertEqual(get_sync_endpoint(), "https://psl.hub")

    def test_db_path_and_git_exclude_hierarchy(self) -> None:
        from harness.telemetry.config import resolve_db_path
        from harness.delivery.constants import GIT_EXCLUDE_PATTERNS
        agyis_db = self.base / "agyis_telemetry.db"
        psl_db = self.base / "psl_telemetry.db"

        with patch.dict(os.environ, {"AGYIS_TELEMETRY_DB": str(agyis_db), "PSL_TELEMETRY_DB": str(psl_db)}, clear=False):
            self.assertEqual(resolve_db_path(), agyis_db.resolve())

        with patch.dict(os.environ, {"PSL_TELEMETRY_DB": str(psl_db)}, clear=False):
            os.environ.pop("AGYIS_TELEMETRY_DB", None)
            self.assertEqual(resolve_db_path(), psl_db.resolve())

        self.assertIn(".agyis/", GIT_EXCLUDE_PATTERNS)
        self.assertIn(".psl/", GIT_EXCLUDE_PATTERNS)


class TestCliDualExecutionMatrix(unittest.TestCase):
    """
    Exhaustive dual assertion suite verifying that primary 'agyis' commands
    execute with clean stderr, while legacy 'psl' commands emit the active
    deprecation warning on stderr without corrupting stdout or JSON streams.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orig_state_dir = os.environ.get("PSL_HARNESS_STATE_DIR")
        self.orig_agyis_state_dir = os.environ.get("AGYIS_HARNESS_STATE_DIR")
        self.orig_brain_dir = os.environ.get("ANTIGRAVITY_BRAIN_DIR")
        self.orig_gemini_brain_dir = os.environ.get("GEMINI_BRAIN_DIR")
        os.environ["PSL_HARNESS_STATE_DIR"] = self.temp_dir.name
        os.environ["AGYIS_HARNESS_STATE_DIR"] = self.temp_dir.name
        default_brain = Path(self.temp_dir.name) / "default_brain"
        default_brain.mkdir(parents=True, exist_ok=True)
        os.environ["ANTIGRAVITY_BRAIN_DIR"] = str(default_brain)
        os.environ["GEMINI_BRAIN_DIR"] = str(default_brain)

    def tearDown(self):
        for mod in DYNAMIC_TEST_MODULES:
            sys.modules.pop(mod, None)
        if self.orig_state_dir is not None:
            os.environ["PSL_HARNESS_STATE_DIR"] = self.orig_state_dir
        else:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
        if self.orig_agyis_state_dir is not None:
            os.environ["AGYIS_HARNESS_STATE_DIR"] = self.orig_agyis_state_dir
        else:
            os.environ.pop("AGYIS_HARNESS_STATE_DIR", None)
        if self.orig_brain_dir is not None:
            os.environ["ANTIGRAVITY_BRAIN_DIR"] = self.orig_brain_dir
        else:
            os.environ.pop("ANTIGRAVITY_BRAIN_DIR", None)
        if self.orig_gemini_brain_dir is not None:
            os.environ["GEMINI_BRAIN_DIR"] = self.orig_gemini_brain_dir
        else:
            os.environ.pop("GEMINI_BRAIN_DIR", None)
        self.temp_dir.cleanup()

    def test_dual_version_invocations(self):
        """Verifies agyis --version is clean, while psl --version emits deprecation warning."""
        from harness import __version__
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main

        self.assertRegex(__version__, r"^1\.0\.0(?:-rc\d+)?$")

        # agyis --version
        with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            with self.assertRaises(SystemExit) as cm1:
                main(["--version"], prog="agyis")
            self.assertEqual(cm1.exception.code, 0)
            self.assertEqual(agyis_err.getvalue(), "")
            self.assertIn(f"agyis-harness {__version__}", agyis_out.getvalue())

        # psl --version
        with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            with self.assertRaises(SystemExit) as cm2:
                deprecated_psl_main(["--version"])
            self.assertEqual(cm2.exception.code, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())
            self.assertIn(f"agyis-harness {__version__}", psl_out.getvalue())

    def test_dual_bare_cli_help(self):
        """Verifies bare 'agyis' and 'psl' with no arguments print help with proper stderr isolation."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main

        # agyis (no args)
        with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            code1 = main([], prog="agyis")
            self.assertEqual(code1, 0)
            self.assertEqual(agyis_err.getvalue(), "")
            self.assertIn("usage: agyis", agyis_out.getvalue())

        # psl (no args)
        with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            code2 = deprecated_psl_main([])
            self.assertEqual(code2, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())
            self.assertIn("usage: psl", psl_out.getvalue())

    def test_dual_status_invocations(self):
        """Verifies status subcommand outputs cleanly on agyis and emits deprecation warning on psl."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main

        with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            code1 = main(["status"], prog="agyis")
            self.assertEqual(code1, 0)
            self.assertEqual(agyis_err.getvalue(), "")
            self.assertIn("Active Lifecycle Hooks", agyis_out.getvalue())

        with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            code2 = deprecated_psl_main(["status"])
            self.assertEqual(code2, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())
            self.assertIn("Active Lifecycle Hooks", psl_out.getvalue())

    def test_dual_skills_json_purity(self):
        """Verifies agyis skills --json and psl skills --json produce identical JSON stdout without contamination."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main

        with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            code1 = main(["skills", "--json"], prog="agyis")
            self.assertEqual(code1, 0)
            self.assertEqual(agyis_err.getvalue(), "")
            data_agyis = json.loads(agyis_out.getvalue().strip())

        with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            code2 = deprecated_psl_main(["skills", "--json"])
            self.assertEqual(code2, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())
            data_psl = json.loads(psl_out.getvalue().strip())

        self.assertEqual(data_agyis, data_psl)
        self.assertGreaterEqual(len(data_agyis), 8)

    def test_dual_agents_json_purity(self):
        """Verifies agyis agents --json and psl agents --json produce identical JSON stdout."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main

        with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            code1 = main(["agents", "--json"], prog="agyis")
            self.assertEqual(code1, 0)
            self.assertEqual(agyis_err.getvalue(), "")
            data_agyis = json.loads(agyis_out.getvalue().strip())

        with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            code2 = deprecated_psl_main(["agents", "--json"])
            self.assertEqual(code2, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())
            data_psl = json.loads(psl_out.getvalue().strip())

        self.assertEqual(data_agyis, data_psl)
        self.assertGreaterEqual(len(data_agyis), 6)

    def test_dual_subagents_json_purity(self):
        """Verifies agyis subagents --json and psl subagents --json produce identical JSON stdout."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main

        with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            code1 = main(["subagents", "--json"], prog="agyis")
            self.assertEqual(code1, 0)
            self.assertEqual(agyis_err.getvalue(), "")
            data_agyis = json.loads(agyis_out.getvalue().strip())

        with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            code2 = deprecated_psl_main(["subagents", "--json"])
            self.assertEqual(code2, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())
            data_psl = json.loads(psl_out.getvalue().strip())

        self.assertEqual(data_agyis, data_psl)

    def test_dual_test_runner_invocations(self):
        """Verifies test runner executes with clean stderr on agyis, warning on psl."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main

        sample_test = "import unittest\nclass S(unittest.TestCase):\n    def test_p(self): self.assertTrue(True)\n"
        sample_file = Path(self.temp_dir.name) / "test_dual_cli_sample.py"
        sample_file.write_text(sample_test, encoding="utf-8")

        with patch("sys.stdout", new_callable=io.StringIO), \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            code1 = main(["test", "-s", self.temp_dir.name], prog="agyis")
            self.assertEqual(code1, 0)
            self.assertNotIn(PSL_DEPRECATION_WARNING.strip(), agyis_err.getvalue())

        with patch("sys.stdout", new_callable=io.StringIO), \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            code2 = deprecated_psl_main(["test", "-s", self.temp_dir.name])
            self.assertEqual(code2, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())

    def test_dual_init_dry_run(self):
        """Verifies init --dry-run executes with clean stderr on agyis, warning on psl."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main
        ws = Path(self.temp_dir.name) / "ws_init"
        ws.mkdir(parents=True)

        with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            code1 = main(["init", str(ws), "--dry-run"], prog="agyis")
            self.assertEqual(code1, 0)
            self.assertEqual(agyis_err.getvalue(), "")

        with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            code2 = deprecated_psl_main(["init", str(ws), "--dry-run"])
            self.assertEqual(code2, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())

    def test_dual_harmonize_dry_run_json(self):
        """Verifies harmonize --dry-run --json runs cleanly on agyis and emits warning on psl."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main
        ws = Path(self.temp_dir.name) / "ws_harm"
        ws.mkdir(parents=True)

        with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            code1 = main(["harmonize", str(ws), "--dry-run", "--json"], prog="agyis")
            self.assertEqual(code1, 0)
            self.assertEqual(agyis_err.getvalue(), "")
            res1 = json.loads(agyis_out.getvalue().strip())
            self.assertTrue(res1["dry_run"])

        with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            code2 = deprecated_psl_main(["harmonize", str(ws), "--dry-run", "--json"])
            self.assertEqual(code2, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())
            res2 = json.loads(psl_out.getvalue().strip())
            self.assertTrue(res2["dry_run"])

        self.assertEqual(res1["workspace_dir"], res2["workspace_dir"])

    def test_dual_doctor_subcommand(self):
        """Verifies doctor runs with clean stderr on agyis, warning on psl."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main

        mock_audit = {
            "summary": {"total": 5, "available": 5, "missing": 0, "outdated": 0},
            "tiers": {},
        }
        with patch("harness.runtime.doctor.run_doctor", return_value=mock_audit), \
             patch("harness.runtime.doctor.print_cli_report"):
            with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
                 patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
                code1 = main(["doctor"], prog="agyis")
                self.assertEqual(code1, 0)
                self.assertEqual(agyis_err.getvalue(), "")

            with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
                 patch("sys.stderr", new_callable=io.StringIO) as psl_err:
                code2 = deprecated_psl_main(["doctor"])
                self.assertEqual(code2, 0)
                self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())

    def test_dual_remote_socket_status(self):
        """Verifies remote socket status runs with clean stderr on agyis, warning on psl."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main

        with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            code1 = main(["remote", "socket", "status"], prog="agyis")
            self.assertEqual(code1, 0)
            self.assertEqual(agyis_err.getvalue(), "")

        with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            code2 = deprecated_psl_main(["remote", "socket", "status"])
            self.assertEqual(code2, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())

    def test_experimental_rea_flags_parsed(self):
        """Verifies --rea and deprecated --experimental-rea flags are accepted cleanly on doctor, init, onboard, and install."""
        from harness.cli import build_parser

        parser = build_parser()

        for subcmd in ("doctor", "init", "onboard", "install"):
            with patch("sys.stderr", new_callable=io.StringIO) as err_rea:
                args_rea = parser.parse_args([subcmd, "--rea"])
                self.assertTrue(args_rea.rea)
                self.assertEqual(err_rea.getvalue(), "")

            with patch("sys.stderr", new_callable=io.StringIO) as err_exp:
                args_exp = parser.parse_args([subcmd, "--experimental-rea"])
                self.assertTrue(args_exp.experimental_rea)
                self.assertTrue(args_exp.rea)
                self.assertIn("DeprecationWarning", err_exp.getvalue())


if __name__ == "__main__":
    unittest.main()
