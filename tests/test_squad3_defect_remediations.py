# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Verification suite for Squad 3 Defect Remediations:
- DEF-BB-028 & DEF-BB-054: 10MB Buffer Expansion
- DEF-BB-029: UnicodeDecodeError resilience in completion fence hook
- DEF-BB-052: command_safety_hook resilience on non-dict JSON
- DEF-BB-053: anti_loop_hook loop detection normalization across metadata drift
- DEF-BB-030: Telemetry harvester type defensive validation
- DEF-BB-031: Completion fence anti-deadlock valve preserved on test failure
- DEF-BB-032: Spec verification classified as "spec" tier and preserves code_dirty
- DEF-BB-033: Submodules and ephemeral scratch files filtered from git dirty checks
- DEF-BB-034: Telemetry schema migration race condition resilience
- DEF-BB-035: Atomic file writes in output compactor hook
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from harness.discovery import get_git_modified_files, is_ephemeral_scratch_path
from harness.hooks import anti_loop_hook, command_safety_hook, completion_fence_hook
from harness.hooks.fence_classifiers import classify_test_tier
from harness.hooks.fence_state import load_state, record_edit, record_verification, save_state
from harness.hooks.fence_tasks import check_command_verification
from harness.hooks.output_compactor_hook import process_payload
from harness.hooks.pre_invocation_hook import MAX_PAYLOAD_BYTES
from harness.hooks.runner import run_hook
from harness.telemetry.extractor import ensure_volume_columns, extract_session
from harness.telemetry.schema import ensure_sync_columns


class TestSquad3DefectRemediations(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_def_bb_028_and_054_10mb_buffer_ceiling(self):
        """DEF-BB-028 & DEF-BB-054: Buffer ceiling is expanded to 10MB (10,485,760 bytes)."""
        self.assertEqual(MAX_PAYLOAD_BYTES, 10_485_760)

        # 1MB payload string through run_hook is not truncated at 512KB
        payload_1mb = json.dumps({"role": "deep_execution", "data": "a" * (1024 * 1024)})
        self.assertGreater(len(payload_1mb), 1_000_000)
        with patch("sys.stdout", new_callable=io.StringIO):
            code = run_hook("anti-drift", payload_str=payload_1mb)
            self.assertEqual(code, 0)

    def test_def_bb_029_completion_fence_binary_stdin_graceful(self):
        """DEF-BB-029: Non-UTF-8 binary stdin does not raise UnicodeDecodeError with exit code 1."""
        raw_binary = b"\xff\xfe\x00\x00invalid-utf8"
        fake_stdin = io.BytesIO(raw_binary)

        with patch("sys.stdin", io.TextIOWrapper(fake_stdin, encoding="latin-1")), \
             patch("sys.stdout", new_callable=io.StringIO) as fake_stdout:
            completion_fence_hook.main()
            output = fake_stdout.getvalue()
            self.assertTrue(len(output) > 0)
            parsed = json.loads(output)
            self.assertIn(parsed.get("decision"), ("allow", "continue"))

    def test_def_bb_052_command_safety_non_dict_json(self):
        """DEF-BB-052: Non-dict JSON payloads do not raise AttributeError."""
        for non_dict in ([1, 2, 3], "string_payload", 12345, True):
            with self.subTest(payload=non_dict):
                with patch("sys.stdin", io.StringIO(json.dumps(non_dict))), \
                     patch("sys.stdout", new_callable=io.StringIO) as fake_stdout:
                    command_safety_hook.main()
                    parsed = json.loads(fake_stdout.getvalue())
                    self.assertEqual(parsed.get("decision"), "allow")

    def test_def_bb_053_anti_loop_metadata_drift_normalization(self):
        """DEF-BB-053: Tool argument comparison ignores non-functional metadata keys."""
        sig1 = {
            "name": "run_command",
            "args": {
                "CommandLine": "ls -la",
                "toolSummary": "List directory 1",
                "WaitMsBeforeAsync": 5000,
                "timeout": 10,
                "description": "desc 1",
            },
        }
        sig2 = {
            "name": "run_command",
            "args": {
                "CommandLine": "ls -la",
                "toolSummary": "List directory 2 (different metadata)",
                "WaitMsBeforeAsync": 1000,
                "timeout": 20,
                "description": "desc 2",
            },
        }
        self.assertTrue(anti_loop_hook._signatures_match(sig1, sig2))

        # Functional differences are NOT ignored
        sig3 = {
            "name": "run_command",
            "args": {
                "CommandLine": "ls -la /tmp",
                "toolSummary": "List directory 1",
            },
        }
        self.assertFalse(anti_loop_hook._signatures_match(sig1, sig3))

    def test_def_bb_030_telemetry_harvester_type_defense(self):
        """DEF-BB-030: Telemetry harvester tolerates non-dict lines and non-integer step indices."""
        transcript_dir = self.state_dir / "user" / "sessions" / "test-session" / "logs" / "conv"
        transcript_dir.mkdir(parents=True, exist_ok=True)
        transcript_file = transcript_dir / "transcript.jsonl"
        with open(transcript_file, "w", encoding="utf-8") as f:
            f.write(json.dumps([1, 2, 3]) + "\n")  # non-dict line
            f.write(json.dumps("random string") + "\n")  # non-dict line
            f.write(json.dumps({"step_index": "not_an_int", "content": "step A"}) + "\n")  # invalid index
            f.write(json.dumps({"step_index": 0, "content": "valid step 0", "created_at": "2026-01-01T00:00:00Z"}) + "\n")
            f.write(json.dumps({"step_index": 1, "type": "USER_INPUT", "content": "user request", "created_at": "2026-01-01T00:01:00Z"}) + "\n")

        # Must parse without TypeError or AttributeError
        data = extract_session(transcript_file)
        self.assertIsNotNone(data)
        session_row, step_rows, tool_rows, interventions = data
        self.assertEqual(session_row["session_id"], "test-session")

    def test_def_bb_031_anti_deadlock_valve_not_reset_on_test_failure(self):
        """DEF-BB-031: Failing a test command does NOT reset block_count to 0."""
        conv_id = "test-deadlock-valve"
        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        state["code_dirty"] = True
        state["block_count"] = 3
        save_state(state, conv_id=conv_id, state_dir=self.state_dir)

        # Run failing test command
        matched = check_command_verification(
            "pnpm test", exit_code=1, conv_id=conv_id, state_dir=self.state_dir, cwd=self.state_dir
        )
        self.assertTrue(matched)

        reloaded = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(reloaded["code_dirty"])
        # block_count must NOT be reset to 0
        self.assertEqual(reloaded.get("block_count"), 3)

    def test_def_bb_032_spec_verification_classified_as_spec_tier(self):
        """DEF-BB-032: Cleanroom spec verification is classified as 'spec' tier and preserves code_dirty."""
        spec_commands = [
            "agyis verify --spec",
            "./agyis verify --spec",
            "rea verify-reconstruction",
            "rea verify",
            "rea evaluate-coverage",
            "python3 -m harness.cli verify",
        ]
        for cmd in spec_commands:
            with self.subTest(cmd=cmd):
                self.assertEqual(classify_test_tier(cmd), "spec")

        conv_id = "test-spec-tier"
        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        state["code_dirty"] = True
        state["spec_dirty"] = True
        save_state(state, conv_id=conv_id, state_dir=self.state_dir)

        # Spec verification success clears spec_dirty, but leaves code_dirty=True
        record_verification(success=True, tier="spec", conv_id=conv_id, state_dir=self.state_dir)
        reloaded = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(reloaded["spec_dirty"])
        self.assertTrue(reloaded["code_dirty"])
        self.assertEqual(reloaded["verified_tier"], "spec")

    def test_def_bb_033_submodule_and_ephemeral_scratch_filtered(self):
        """DEF-BB-033: Submodules and ephemeral scratch files are filtered from git modified checks."""
        repo_dir = self.state_dir / "test_repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)

        # Initial commit
        (repo_dir / "README.md").write_text("Hello", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_dir, check=True, capture_output=True)

        # Add a scratch file
        (repo_dir / "scratch").mkdir()
        (repo_dir / "scratch" / "probe.py").write_text("print(1)", encoding="utf-8")

        # Add a mock submodule directory
        (repo_dir / "vendor").mkdir()
        (repo_dir / "vendor" / "submod").mkdir()
        (repo_dir / "vendor" / "submod" / ".git").write_text("gitdir: ../../.git/modules/submod", encoding="utf-8")
        (repo_dir / "vendor" / "submod" / "sub.py").write_text("submodule code", encoding="utf-8")

        # Write .gitmodules
        (repo_dir / ".gitmodules").write_text("[submodule \"vendor/submod\"]\n\tpath = vendor/submod\n", encoding="utf-8")

        # Untracked probe.py in scratch and submodule should be filtered out
        mods = get_git_modified_files(cwd=repo_dir)
        self.assertNotIn("scratch/probe.py", mods)
        self.assertNotIn("vendor/submod", mods)
        self.assertNotIn("vendor/submod/sub.py", mods)

    def test_def_bb_034_telemetry_migration_race_condition(self):
        """DEF-BB-034: ALTER TABLE duplicate column name does not crash migration."""
        conn = sqlite3.connect(":memory:")
        ensure_sync_columns(conn)
        ensure_volume_columns(conn)

        # Running a second time simulates concurrent migration where columns exist
        ensure_sync_columns(conn)
        ensure_volume_columns(conn)

        # Verify columns exist
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(sessions)")
        cols = {r[1] for r in cur.fetchall()}
        self.assertIn("origin_developer", cols)
        self.assertIn("remote_synced_at", cols)

    def test_def_bb_035_output_compactor_atomic_writes(self):
        """DEF-BB-035: Output compactor writes state files atomically."""
        output = "line\n" * 1000
        payload = {
            "conversationId": "test-atomic",
            "stepIdx": 1,
            "toolCall": {"name": "run_command", "args": {"CommandLine": "ls"}},
            "toolResponse": {"output": output, "exitCode": 0},
        }
        res = process_payload(payload, state_dir=self.state_dir)
        self.assertTrue(res["wasCompacted"])
        compactor_meta = self.state_dir / "compactor_test-atomic.json"
        self.assertTrue(compactor_meta.exists())
        data = json.loads(compactor_meta.read_text(encoding="utf-8"))
        self.assertEqual(data["conversationId"], "test-atomic")


if __name__ == "__main__":
    unittest.main()
