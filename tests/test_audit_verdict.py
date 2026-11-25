#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Unit Tests for Out-of-Band Auditor Verdict Schema and Validation (Issue #66).
Sub-second benchmark invariant: <0.05s execution time under complete isolation.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from harness.commands.audit import cmd_audit
from harness.subagents.verdict import (
    AuditVerdict,
    generate_audit_verdict,
    validate_audit_verdict,
)


class TestAuditVerdict(unittest.TestCase):
    """Hermetic unit tests for AuditVerdict data model and validation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_verdict_file(self):
        """Missing audit verdict file returns False with appropriate reason."""
        valid, reason, verdict = validate_audit_verdict(self.workspace)
        self.assertFalse(valid)
        self.assertIn("Out-of-band auditor clearance missing", reason)
        self.assertIsNone(verdict)

    def test_corrupted_json(self):
        """Corrupted JSON verdict returns False."""
        art_dir = self.workspace / ".agents" / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)
        (art_dir / "audit_verdict.json").write_text("{bad-json:", encoding="utf-8")

        valid, reason, verdict = validate_audit_verdict(self.workspace)
        self.assertFalse(valid)
        self.assertIn("Corrupted audit verdict file", reason)
        self.assertIsNone(verdict)

    def test_valid_verdict_confirmed(self):
        """Valid VICTORY CONFIRMED verdict returns True with AuditVerdict object."""
        verdict = generate_audit_verdict(
            workspace_dir=self.workspace,
            task_id="ISSUE-66",
            verdict="VICTORY CONFIRMED",
            test_suite_result={"exit_code": 0, "total_tests": 100, "passed_tests": 100, "failed_tests": 0},
            doctor_result={"ok_count": 10, "missing_count": 0, "outdated_count": 0},
        )
        self.assertTrue(verdict.path.exists())

        valid, reason, loaded = validate_audit_verdict(self.workspace)
        self.assertTrue(valid)
        self.assertIsNone(reason)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.task_id, "ISSUE-66")
        self.assertEqual(loaded.verdict, "VICTORY CONFIRMED")
        self.assertEqual(loaded.test_suite["exit_code"], 0)

    def test_valid_pass_verdict(self):
        """Verdict 'PASS' with non-zero executed tests and passing AFF is accepted as valid clearance."""
        generate_audit_verdict(
            workspace_dir=self.workspace,
            task_id="TASK-PASS",
            verdict="PASS",
            test_suite_result={"exit_code": 0, "total_tests": 50, "passed_tests": 50, "failed_tests": 0},
            aff_result={"status": "PASS", "score": 100.0},
        )
        valid, reason, loaded = validate_audit_verdict(self.workspace)
        self.assertTrue(valid, f"Unexpected rejection: {reason}")
        self.assertIsNone(reason)
        self.assertEqual(loaded.verdict, "PASS")

    def test_zero_tests_or_failing_aff_rejected(self):
        """Gate 2 rejects VICTORY CONFIRMED when total_tests <= 0 or AFF audit failed."""
        generate_audit_verdict(
            workspace_dir=self.workspace,
            task_id="ZERO-TESTS",
            verdict="VICTORY CONFIRMED",
            test_suite_result={"exit_code": 0, "total_tests": 0, "passed_tests": 0, "failed_tests": 0},
        )
        valid_z, reason_z, _ = validate_audit_verdict(self.workspace)
        self.assertFalse(valid_z)
        self.assertIn("zero executed tests", reason_z)

        generate_audit_verdict(
            workspace_dir=self.workspace,
            task_id="BAD-AFF",
            verdict="VICTORY CONFIRMED",
            test_suite_result={"exit_code": 0, "total_tests": 10, "passed_tests": 10, "failed_tests": 0},
            aff_result={"status": "FAIL", "score": 50.0},
        )
        valid_a, reason_a, _ = validate_audit_verdict(self.workspace)
        self.assertFalse(valid_a)
        self.assertIn("Architectural fitness audit reported FAIL", reason_a)

    def test_rejected_verdict(self):
        """Rejected verdict returns False and cites auditor rejection."""
        generate_audit_verdict(
            workspace_dir=self.workspace,
            task_id="ISSUE-66",
            verdict="REJECTED",
        )
        valid, reason, loaded = validate_audit_verdict(self.workspace)
        self.assertFalse(valid)
        self.assertIn("Auditor rejected victory", reason)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.verdict, "REJECTED")

    def test_test_suite_failure_rejection(self):
        """Failed tests reported in verdict lead to clearance rejection."""
        generate_audit_verdict(
            workspace_dir=self.workspace,
            task_id="ISSUE-FAIL",
            verdict="VICTORY CONFIRMED",
            test_suite_result={"exit_code": 1, "failed_tests": 2, "total_tests": 10},
        )
        valid, reason, loaded = validate_audit_verdict(self.workspace)
        self.assertFalse(valid)
        self.assertIn("Test suite reported failure", reason)
        self.assertIsNotNone(loaded)

    def test_stale_verdict_rejection(self):
        """Verdict older than max_age_seconds is rejected as stale."""
        stale_time = (datetime.now(timezone.utc) - timedelta(seconds=7200)).isoformat()
        verdict = generate_audit_verdict(
            workspace_dir=self.workspace,
            task_id="STALE-001",
            verdict="VICTORY CONFIRMED",
            test_suite_result={"exit_code": 0, "total_tests": 25, "passed_tests": 25, "failed_tests": 0},
        )
        data = verdict.to_dict()
        data["timestamp"] = stale_time
        verdict.path.write_text(json.dumps(data), encoding="utf-8")

        valid, reason, loaded = validate_audit_verdict(self.workspace, max_age_seconds=3600)
        self.assertFalse(valid)
        self.assertIn("stale", reason)

        # Allow synthetic ignores staleness
        valid_synth, reason_synth, _ = validate_audit_verdict(
            self.workspace, max_age_seconds=3600, allow_synthetic=True
        )
        self.assertTrue(valid_synth)
        self.assertIsNone(reason_synth)

    def test_candidate_discovery_locations(self):
        """Tests discovery in env var, teamwork dir, brain dir, and artifact glob."""
        valid_suite = {"exit_code": 0, "total_tests": 12, "passed_tests": 12, "failed_tests": 0}
        valid_aff = {"status": "PASS", "score": 100.0}

        # 1. Environment variable override
        custom_file = self.workspace / "custom_verdict.json"
        generate_audit_verdict(
            workspace_dir=self.workspace,
            task_id="ENV-CUSTOM",
            test_suite_result=valid_suite,
            aff_result=valid_aff,
            output_path=custom_file,
        )
        with patch.dict(os.environ, {"AGYIS_AUDIT_VERDICT_PATH": str(custom_file)}):
            valid, _, loaded = validate_audit_verdict(self.workspace)
            self.assertTrue(valid)
            self.assertEqual(loaded.task_id, "ENV-CUSTOM")

        # 2. Teamwork directory
        teamwork_file = self.workspace / ".agents" / "teamwork" / "audit_verdict.json"
        generate_audit_verdict(
            workspace_dir=self.workspace,
            task_id="TEAMWORK-01",
            test_suite_result=valid_suite,
            aff_result=valid_aff,
            output_path=teamwork_file,
        )
        valid, _, loaded = validate_audit_verdict(self.workspace)
        self.assertTrue(valid)
        self.assertEqual(loaded.task_id, "TEAMWORK-01")

        # 3. Brain directory
        brain_dir = self.workspace / "brain"
        brain_file = brain_dir / "audit_verdict.json"
        generate_audit_verdict(
            workspace_dir=self.workspace,
            task_id="BRAIN-01",
            test_suite_result=valid_suite,
            aff_result=valid_aff,
            output_path=brain_file,
        )
        # Remove teamwork file to test brain dir
        teamwork_file.unlink()
        valid, _, loaded = validate_audit_verdict(self.workspace, brain_dir=brain_dir)
        self.assertTrue(valid)
        self.assertEqual(loaded.task_id, "BRAIN-01")

    def test_cli_audit_certify_and_verdict(self):
        """Tests cmd_audit certify (--skip-tests -> PROVISIONAL/rc 1; full pass -> VICTORY CONFIRMED/rc 0) and verdict."""
        # 1. verdict query before certify -> returns 1
        with patch("sys.stdout", new=io.StringIO()):
            rc = cmd_audit(argparse.Namespace(stage="verdict", json=False, workspace=self.workspace))
            self.assertEqual(rc, 1)

        # 2. certify with skip-tests -> emits PROVISIONAL and returns rc 1; Gate 2 rejects PROVISIONAL
        with patch("sys.stdout", new=io.StringIO()) as skip_out:
            rc_skip = cmd_audit(
                argparse.Namespace(
                    stage="certify",
                    task_id="CLI-TEST-SKIP",
                    verdict="VICTORY CONFIRMED",
                    skip_tests=True,
                    json=True,
                    workspace=self.workspace,
                )
            )
            self.assertEqual(rc_skip, 1)
            skip_data = json.loads(skip_out.getvalue().strip())
            self.assertEqual(skip_data["verdict"], "PROVISIONAL")

        with patch("sys.stdout", new=io.StringIO()) as v_skip_out:
            rc_v_skip = cmd_audit(argparse.Namespace(stage="verdict", json=True, workspace=self.workspace))
            self.assertEqual(rc_v_skip, 1)
            self.assertFalse(json.loads(v_skip_out.getvalue().strip())["valid"])

        # 3. full certify with executed tests & passing AFF -> returns 0 and Gate 2 grants clearance
        class _FakeProc:
            returncode = 0
            stdout = ""
            stderr = "Ran 42 tests in 0.100s\n\nOK\n"

        with patch("subprocess.run", return_value=_FakeProc()), \
             patch("harness.runtime.doctor.audit_environment", return_value={"summary": {"ok": 5, "missing": 0, "outdated": 0}}), \
             patch("sys.stdout", new=io.StringIO()) as ok_out:
            rc = cmd_audit(
                argparse.Namespace(
                    stage="certify",
                    task_id="CLI-TEST-001",
                    verdict="VICTORY CONFIRMED",
                    skip_tests=False,
                    json=True,
                    workspace=self.workspace,
                )
            )
            self.assertEqual(rc, 0)
            cert_data = json.loads(ok_out.getvalue().strip())
            self.assertEqual(cert_data["verdict"], "VICTORY CONFIRMED")
            self.assertEqual(cert_data["test_suite"]["total_tests"], 42)
            self.assertEqual(cert_data["aff_audit"]["status"], "PASS")

        # 4. verdict query after valid certify -> returns 0
        with patch("sys.stdout", new=io.StringIO()):
            rc = cmd_audit(argparse.Namespace(stage="verdict", json=True, workspace=self.workspace))
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
