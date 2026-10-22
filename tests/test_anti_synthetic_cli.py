# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
CLI Integration & Lifecycle Hook Contract Tests: Anti-Synthetic Doctor & Mutation (RFC-051 Phase 3.1).
"""

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from harness.cli import build_parser
from harness.commands.doctor import cmd_doctor
from harness.commands.test import cmd_test
from harness.hooks import completion_fence_hook


class TestAntiSyntheticCLI(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.state_dir = self.root / ".agyis" / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _write_file(self, filename: str, content: str) -> Path:
        p = self.root / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def test_cli_parser_recognizes_new_flags(self):
        """Validates that doctor --anti-synthetic and test --mutation parse correctly."""
        parser = build_parser("agyis")

        args_doc = parser.parse_args(["doctor", "--anti-synthetic", "--json"])
        self.assertTrue(args_doc.anti_synthetic)
        self.assertTrue(args_doc.json)

        args_test = parser.parse_args(["test", "--mutation", "--json"])
        self.assertTrue(args_test.mutation)
        self.assertTrue(args_test.json)

    def test_doctor_anti_synthetic_clean_returns_zero(self):
        """agyis doctor --anti-synthetic on clean tests exits 0."""
        self._write_file("tests/test_good.py", "def test_val():\n    assert 2 + 2 == 4\n")

        parser = build_parser("agyis")
        args = parser.parse_args(["doctor", "--anti-synthetic", "--json"])

        stdout_buf = io.StringIO()
        with patch("pathlib.Path.cwd", return_value=self.root), patch("sys.stdout", stdout_buf):
            code = cmd_doctor(args)

        self.assertEqual(code, 0)
        report = json.loads(stdout_buf.getvalue())
        self.assertTrue(report["passed"])
        self.assertEqual(report["hard_rejects_count"], 0)

    def test_doctor_anti_synthetic_hard_reject_returns_one(self):
        """agyis doctor --anti-synthetic exits 1 on hard reject test smells."""
        self._write_file("tests/test_bad.py", "def test_bad():\n    assert 1 == 1\n")

        parser = build_parser("agyis")
        args = parser.parse_args(["doctor", "--anti-synthetic"])

        stdout_buf = io.StringIO()
        with patch("pathlib.Path.cwd", return_value=self.root), patch("sys.stdout", stdout_buf):
            code = cmd_doctor(args)

        self.assertEqual(code, 1)
        output = stdout_buf.getvalue()
        self.assertIn("[HARD REJECT]", output)
        self.assertIn("zero-state-tautology", output)

    def test_test_mutation_probe_clean_diff_returns_zero(self):
        """agyis test --mutation on clean working tree exits 0 with 100% score."""
        parser = build_parser("agyis")
        args = parser.parse_args(["test", "--mutation", "--json"])

        stdout_buf = io.StringIO()
        with patch("pathlib.Path.cwd", return_value=self.root), patch("sys.stdout", stdout_buf):
            code = cmd_test(args)

        self.assertEqual(code, 0)
        report = json.loads(stdout_buf.getvalue())
        self.assertEqual(report["total_mutants"], 0)
        self.assertEqual(report["score"], 100.0)

    def test_completion_fence_ast_smell_blocks_completion(self):
        """Completion fence stops agent and retains code_dirty when modified test file contains smells."""
        test_file = self._write_file("tests/test_smelly.py", "def test_synthetic():\n    assert 1 == 1\n")

        conv_id = "test_conv_smell"
        completion_fence_hook.record_edit(
            str(test_file), conv_id=conv_id, state_dir=self.state_dir, cwd=self.root
        )

        res = completion_fence_hook.evaluate_stop(
            conv_id=conv_id,
            state_dir=self.state_dir,
            cwd=self.root,
        )

        self.assertEqual(res.get("decision"), "continue")
        self.assertIn("Anti-Synthetic AST Linter Error", res.get("reason", ""))
        self.assertIn("zero-state-tautology", res.get("reason", ""))

    def test_completion_fence_commit_gate_requires_mutation_verification(self):
        """Commit gate blocks when modified code contains unverified mutants."""
        impl_file = self._write_file(
            "app/compute.py",
            "def compute(x):\n    if x > 10:\n        return x * 2\n    return x\n",
        )
        conv_id = "test_conv_commit"
        completion_fence_hook.record_edit(
            str(impl_file), conv_id=conv_id, state_dir=self.state_dir, cwd=self.root
        )

        # Mark tier pkg to satisfy test tier check
        state = completion_fence_hook.load_state(conv_id=conv_id, state_dir=self.state_dir)
        state["verified_tier"] = "pkg"
        completion_fence_hook.save_state(state, conv_id=conv_id, state_dir=self.state_dir)

        # Mock generate_mutants_for_diff to return an unverified mutant
        fake_mutant = completion_fence_hook.load_state(conv_id=conv_id, state_dir=self.state_dir)
        with patch("harness.mutation.micro_probe.generate_mutants_for_diff") as mock_gen:
            from harness.mutation.micro_probe import Mutant
            mock_gen.return_value = [
                Mutant(
                    mutant_id="mut_1",
                    file_path=impl_file,
                    function_name="compute",
                    line_number=2,
                    operator="condition_inversion",
                    original_source="",
                    mutated_source="",
                    diff="",
                )
            ]

            res = completion_fence_hook.evaluate_stop(
                conv_id=conv_id,
                state_dir=self.state_dir,
                cwd=self.root,
                payload={"gate_type": "commit"},
            )

            self.assertEqual(res.get("decision"), "deny")
            self.assertIn("Commit Verification Required", res.get("reason", ""))
            self.assertIn("unverified mutants", res.get("reason", ""))


if __name__ == "__main__":
    unittest.main()
