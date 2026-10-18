# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unit tests for 'verify' CLI subcommand (DEF-03 / ADR-028).
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from harness.cli import build_parser, main as cli_main
from harness.commands.verify import cmd_verify


class TestVerifyCommand(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_verify_subparser_arguments(self) -> None:
        """Verifies CLI argument parsing for 'verify' subparser."""
        parser = build_parser()
        args = parser.parse_args(["verify", "--spec", "-w", "/tmp/ws", "--json"])
        self.assertEqual(args.subcommand, "verify")
        self.assertTrue(args.spec)
        self.assertEqual(args.workspace, Path("/tmp/ws"))
        self.assertTrue(args.json)

        # Default args
        args_default = parser.parse_args(["verify"])
        self.assertEqual(args_default.subcommand, "verify")
        self.assertFalse(args_default.spec)
        self.assertIsNone(args_default.workspace)
        self.assertFalse(args_default.json)

    def test_cmd_verify_clean_specs_present(self) -> None:
        """Verifies cmd_verify returns 0 when cleanroom specs exist in docs/specs/**."""
        specs_dir = self.workspace / "docs" / "specs"
        specs_dir.mkdir(parents=True, exist_ok=True)
        (specs_dir / "architecture.md").write_text("# Cleanroom Spec", encoding="utf-8")

        args = argparse.Namespace(
            workspace=self.workspace,
            spec=True,
            json=False,
        )
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = cmd_verify(args)
        self.assertEqual(code, 0)
        self.assertIn("Cleanroom specifications verified", buf.getvalue())

    def test_cmd_verify_clean_specs_json_output(self) -> None:
        """Verifies cmd_verify --json returns valid JSON summary."""
        specs_dir = self.workspace / "docs" / "specs"
        specs_dir.mkdir(parents=True, exist_ok=True)
        (specs_dir / "api.json").write_text("{}", encoding="utf-8")

        args = argparse.Namespace(
            workspace=self.workspace,
            spec=True,
            json=True,
        )
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = cmd_verify(args)
        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["status"], "verified")
        self.assertEqual(data["specs_count"], 1)

    def test_cmd_verify_valid_manifest(self) -> None:
        """Verifies cmd_verify returns 0 when .agents/ledger/manifest.json is verified."""
        ledger_dir = self.workspace / ".agents" / "ledger"
        ledger_dir.mkdir(parents=True, exist_ok=True)
        manifest_payload = {
            "status": "verified",
            "evidence_hash": "a" * 64,
            "obligations": [{"id": "OBL-01", "status": "satisfied"}],
        }
        (ledger_dir / "manifest.json").write_text(json.dumps(manifest_payload), encoding="utf-8")

        args = argparse.Namespace(
            workspace=self.workspace,
            spec=False,
            json=False,
        )
        buf = io.StringIO()
        with patch("shutil.which", return_value=None), patch("sys.stdout", buf):
            code = cmd_verify(args)
        self.assertEqual(code, 0)
        self.assertIn("Cleanroom verification passed", buf.getvalue())

    def test_cmd_verify_invalid_manifest_returns_1(self) -> None:
        """Verifies cmd_verify returns 1 when manifest exists but is invalid schema/status."""
        ledger_dir = self.workspace / ".agents" / "ledger"
        ledger_dir.mkdir(parents=True, exist_ok=True)
        # Invalid manifest: missing satisfied obligations and bad status
        manifest_payload = {
            "status": "pending",
            "evidence_hash": "invalid-hash",
            "obligations": [{"status": "failed"}],
        }
        (ledger_dir / "manifest.json").write_text(json.dumps(manifest_payload), encoding="utf-8")

        args = argparse.Namespace(
            workspace=self.workspace,
            spec=False,
            json=False,
        )
        err_buf = io.StringIO()
        with patch("shutil.which", return_value=None), patch("sys.stderr", err_buf):
            code = cmd_verify(args)
        self.assertEqual(code, 1)
        self.assertIn("Verification failed", err_buf.getvalue())

    def test_cmd_verify_invalid_manifest_json(self) -> None:
        """Verifies cmd_verify returns 1 with failed JSON when manifest is invalid."""
        ledger_dir = self.workspace / ".agents" / "ledger"
        ledger_dir.mkdir(parents=True, exist_ok=True)
        (ledger_dir / "manifest.json").write_text("{bad-json}", encoding="utf-8")

        args = argparse.Namespace(
            workspace=self.workspace,
            spec=False,
            json=True,
        )
        out_buf = io.StringIO()
        with patch("shutil.which", return_value=None), patch("sys.stdout", out_buf):
            code = cmd_verify(args)
        self.assertEqual(code, 1)
        data = json.loads(out_buf.getvalue())
        self.assertEqual(data["status"], "failed")

    def test_cmd_verify_delegates_to_rea_when_available(self) -> None:
        """Verifies delegation to 'rea verify-reconstruction' when rea is in PATH."""
        args = argparse.Namespace(
            workspace=self.workspace,
            spec=False,
            json=False,
        )
        mock_proc = subprocess.CompletedProcess(
            args=["rea", "verify-reconstruction"],
            returncode=0,
            stdout="REA reconstruction verified: 10/10 obligations",
            stderr="",
        )
        with patch("shutil.which", return_value="/usr/local/bin/rea"), patch(
            "subprocess.run", return_value=mock_proc
        ) as mock_run, patch("sys.stdout", new_callable=io.StringIO):
            code = cmd_verify(args)
            self.assertEqual(code, 0)
            mock_run.assert_called_once_with(
                ["rea", "verify-reconstruction"],
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
            )

    def test_cmd_verify_rea_failure_returns_1(self) -> None:
        """Verifies that failing rea verify-reconstruction delegates and returns error code."""
        args = argparse.Namespace(
            workspace=self.workspace,
            spec=False,
            json=False,
        )
        mock_proc = subprocess.CompletedProcess(
            args=["rea", "verify-reconstruction"],
            returncode=1,
            stdout="",
            stderr="Unsatisfied obligation: OBL-042",
        )
        with patch("shutil.which", return_value="/usr/local/bin/rea"), patch(
            "subprocess.run", return_value=mock_proc
        ), patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code = cmd_verify(args)
            self.assertEqual(code, 1)
            self.assertIn("Verification failed", mock_err.getvalue())
            self.assertIn("Unsatisfied obligation: OBL-042", mock_err.getvalue())

    def test_cli_main_verify_integration(self) -> None:
        """Verifies running 'verify' through harness.cli.main dispatcher."""
        specs_dir = self.workspace / "docs" / "specs"
        specs_dir.mkdir(parents=True, exist_ok=True)
        (specs_dir / "protocol.md").write_text("# Protocol", encoding="utf-8")

        with patch("sys.stdout", io.StringIO()):
            ret = cli_main(["verify", "--spec", "-w", str(self.workspace)])
            self.assertEqual(ret, 0)

    def test_cmd_verify_clears_spec_dirty(self) -> None:
        """Verifies that cmd_verify clears spec_dirty state in completion fence upon success."""
        from harness.hooks.completion_fence_hook import load_state, record_edit

        specs_dir = self.workspace / "docs" / "specs"
        specs_dir.mkdir(parents=True, exist_ok=True)
        spec_file = specs_dir / "clean_contract.md"
        spec_file.write_text("# Contract", encoding="utf-8")

        # Simulate spec edit dirtying state
        record_edit(str(spec_file), conv_id="test_verify_clear", cwd=str(self.workspace))
        st_before = load_state(conv_id="test_verify_clear")
        self.assertTrue(st_before.get("spec_dirty"))

        args = argparse.Namespace(
            workspace=self.workspace,
            spec=True,
            json=False,
        )
        with patch("harness.commands.verify.clear_spec_dirty") as mock_clear, \
             patch("sys.stdout", new_callable=io.StringIO):
            code = cmd_verify(args)
            self.assertEqual(code, 0)
            mock_clear.assert_called_once()


if __name__ == "__main__":
    unittest.main()
