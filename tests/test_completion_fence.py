#!/usr/bin/env python3
"""
Unit and integration contract tests for harness/hooks/completion_fence_hook.py
Governing ADRs: ADR-014, ADR-015, ADR-022
"""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from harness.hooks import completion_fence_hook
from harness.hooks.completion_fence_hook import (
    evaluate_stop,
    get_state_file,
    is_code_file,
    load_state,
    record_edit,
    record_verification,
    reset_state,
)


class TestCompletionFenceHook(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name)
        self.orig_state_env = os.environ.get("PSL_HARNESS_STATE_DIR")
        os.environ["PSL_HARNESS_STATE_DIR"] = str(self.state_dir)

    def tearDown(self):
        if self.orig_state_env is not None:
            os.environ["PSL_HARNESS_STATE_DIR"] = self.orig_state_env
        else:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
        self.temp_dir.cleanup()

    def test_is_code_file_exemptions(self):
        """Verifies documentation, assets, lockfiles, and git configs are exempt."""
        exempt_paths = [
            "README.md",
            "docs/architecture.md",
            "guide.markdown",
            "notes.txt",
            "spec.rst",
            "doc.adoc",
            "logo.png",
            "banner.jpg",
            "photo.jpeg",
            "icon.ico",
            "illustration.svg",
            "anim.gif",
            "preview.webp",
            ".gitignore",
            ".gitattributes",
            ".editorconfig",
            "package-lock.json",
            "uv.lock",
            "poetry.lock",
            "Cargo.lock",
            "yarn.lock",
            "pnpm-lock.yaml",
            "custom.lock",
        ]
        for path in exempt_paths:
            with self.subTest(path=path):
                self.assertFalse(
                    is_code_file(path),
                    f"Expected {path} to be exempt from code verification",
                )

    def test_is_code_file_code_detection(self):
        """Verifies code file extensions are correctly flagged as code."""
        code_paths = [
            "harness/cli.py",
            "types/index.ts",
            "components/App.tsx",
            "src/index.js",
            "src/component.jsx",
            "src/main.rs",
            "cmd/main.go",
            "native/lib.c",
            "native/lib.cpp",
            "native/header.h",
            "native/header.hpp",
            "src/Main.java",
            "src/App.kt",
            "scripts/deploy.sh",
            "scripts/build.bash",
            "styles/main.css",
            "styles/app.scss",
            "templates/page.html",
        ]
        for path in code_paths:
            with self.subTest(path=path):
                self.assertTrue(
                    is_code_file(path),
                    f"Expected {path} to be recognized as code",
                )

    def test_clean_state_evaluate_stop_allows(self):
        """An initial clean state must allow stopping immediately."""
        conv_id = "test-clean-conv"
        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res.get("decision"), "allow")

    def test_exempt_file_edit_does_not_dirty_state(self):
        """Editing an exempt file (e.g. .md, .png) does not mark state dirty."""
        conv_id = "test-exempt-conv"
        record_edit("README.md", conv_id=conv_id, state_dir=self.state_dir)
        record_edit("assets/logo.png", conv_id=conv_id, state_dir=self.state_dir)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])
        self.assertEqual(state["last_modified_files"], [])

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res.get("decision"), "allow")

    def test_code_edit_dirties_state_and_blocks_stop(self):
        """Editing code marks state dirty and stops are blocked up to 2 times."""
        conv_id = "test-dirty-conv"
        record_edit("harness/cli.py", conv_id=conv_id, state_dir=self.state_dir)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(state["code_dirty"])
        self.assertIn("harness/cli.py", state["last_modified_files"])
        self.assertEqual(state["block_count"], 0)

        # First stop evaluation: blocked
        res1 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res1.get("decision"), "continue")
        self.assertIn("Verification Required", res1.get("reason", ""))
        self.assertIn("harness/cli.py", res1.get("reason", ""))

        state1 = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(state1["block_count"], 1)

        # Second stop evaluation: blocked
        res2 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res2.get("decision"), "continue")
        self.assertIn("Verification Required", res2.get("reason", ""))

        state2 = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(state2["block_count"], 2)

    def test_anti_deadlock_valve_trips_after_two_blocks(self):
        """After 2 blocked stops, the 3rd attempt must trip the anti-deadlock valve and allow exit."""
        conv_id = "test-anti-deadlock"
        record_edit("harness/hooks/completion_fence_hook.py", conv_id=conv_id, state_dir=self.state_dir)

        # Block 1
        res1 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res1.get("decision"), "continue")

        # Block 2
        res2 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res2.get("decision"), "continue")

        # Block 3: Anti-deadlock valve trips!
        res3 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res3.get("decision"), "allow")
        self.assertIn("warning", res3)
        self.assertIn("Anti-deadlock valve tripped after 2 verification blocks", res3["warning"])

    def test_record_edit_rearms_fence_by_resetting_block_count(self):
        """A new code edit resets block_count to 0 so the fence re-arms."""
        conv_id = "test-rearm"
        record_edit("src/a.py", conv_id=conv_id, state_dir=self.state_dir)

        # Block once
        res1 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res1.get("decision"), "continue")
        state1 = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(state1["block_count"], 1)

        # New edit must reset block_count to 0
        record_edit("src/b.py", conv_id=conv_id, state_dir=self.state_dir)
        state2 = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(state2["block_count"], 0)
        self.assertIn("src/b.py", state2["last_modified_files"])

    def test_verification_success_clears_dirty_and_resets_block_count(self):
        """Successful verification clears code_dirty, resets block_count, and sets timestamp."""
        conv_id = "test-verify-success"
        record_edit("harness/cli.py", conv_id=conv_id, state_dir=self.state_dir)

        # Trip 1 block
        evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        state_blocked = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(state_blocked["block_count"], 1)

        # Record successful test run
        record_verification(success=True, conv_id=conv_id, state_dir=self.state_dir)

        state_cleared = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state_cleared["code_dirty"])
        self.assertEqual(state_cleared["last_modified_files"], [])
        self.assertEqual(state_cleared["block_count"], 0)
        self.assertIsNotNone(state_cleared["last_verified_at"])

        # Stop should now be allowed
        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res.get("decision"), "allow")

    def test_verification_failure_preserves_dirty(self):
        """Failed verification keeps code_dirty = True and does not clear block_count."""
        conv_id = "test-verify-fail"
        record_edit("harness/cli.py", conv_id=conv_id, state_dir=self.state_dir)

        record_verification(success=False, conv_id=conv_id, state_dir=self.state_dir)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(state["code_dirty"])
        self.assertIn("harness/cli.py", state["last_modified_files"])

        # Stop must remain blocked
        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res.get("decision"), "continue")

    def test_reset_state(self):
        """reset_state returns state to initial clean baseline."""
        conv_id = "test-reset"
        record_edit("harness/cli.py", conv_id=conv_id, state_dir=self.state_dir)
        reset_state(conv_id=conv_id, state_dir=self.state_dir)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])
        self.assertEqual(state["last_modified_files"], [])
        self.assertEqual(state["block_count"], 0)
        self.assertIsNone(state["last_verified_at"])

    def test_conversation_isolation(self):
        """Edits in conversation A do not affect conversation B."""
        record_edit("harness/cli.py", conv_id="conv-a", state_dir=self.state_dir)

        res_b = evaluate_stop(conv_id="conv-b", state_dir=self.state_dir)
        self.assertEqual(res_b.get("decision"), "allow")

        res_a = evaluate_stop(conv_id="conv-a", state_dir=self.state_dir)
        self.assertEqual(res_a.get("decision"), "continue")

    def test_corrupted_state_recovers_gracefully(self):
        """Corrupted JSON in state file does not raise an exception."""
        conv_id = "test-corrupted"
        state_file = get_state_file(conv_id, self.state_dir)
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("{corrupt-json", encoding="utf-8")

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])
        self.assertEqual(state["block_count"], 0)

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res.get("decision"), "allow")

    def test_pre_tool_use_protojson_contract(self):
        """Defect 3 Contract Test: passes real Antigravity PreToolUse payload, marks state dirty, emits allow."""
        payload = {
            "conversationId": "pre-tool-conv-123",
            "toolCall": {
                "name": "write_to_file",
                "args": {
                    "TargetFile": "src/app.py",
                },
            },
        }
        buf = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", buf):
            completion_fence_hook.main()

        out = json.loads(buf.getvalue().strip())
        self.assertEqual(out.get("decision"), "allow")

        # Verify state is marked dirty
        state = load_state(conv_id="pre-tool-conv-123", state_dir=self.state_dir)
        self.assertTrue(state.get("code_dirty"))
        self.assertIn("src/app.py", state.get("last_modified_files", []))

        # Stop is now blocked
        res_stop = evaluate_stop(conv_id="pre-tool-conv-123", state_dir=self.state_dir)
        self.assertEqual(res_stop.get("decision"), "continue")
        self.assertIn("src/app.py", res_stop.get("reason", ""))

    def test_null_conversation_id_handling(self):
        """Defect 6: Null or missing conversationId falls back cleanly to 'default'."""
        payload = {
            "conversationId": None,
            "toolCall": {
                "name": "replace_file_content",
                "args": {
                    "TargetFile": "src/index.ts",
                },
            },
        }
        buf = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", buf):
            completion_fence_hook.main()

        out = json.loads(buf.getvalue().strip())
        self.assertEqual(out.get("decision"), "allow")

        state = load_state(conv_id="default", state_dir=self.state_dir)
        self.assertTrue(state.get("code_dirty"))
        self.assertIn("src/index.ts", state.get("last_modified_files", []))

    def test_cli_hook_stdin_stdout_contract(self):
        """Validates the CLI hook entrypoint executes correctly via stdin/stdout."""
        # 1. Clean stop evaluates to allow
        buf1 = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps({"conversationId": "cli-contract-conv"}))), patch("sys.stdout", buf1):
            completion_fence_hook.main()
        out1 = json.loads(buf1.getvalue().strip())
        self.assertEqual(out1.get("decision"), "allow")

        # 2. Record edit via action
        buf2 = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps({
            "conversationId": "cli-contract-conv",
            "action": "record_edit",
            "file_path": "src/main.py",
        }))), patch("sys.stdout", buf2):
            completion_fence_hook.main()
        out2 = json.loads(buf2.getvalue().strip())
        self.assertEqual(out2.get("status"), "ok")

        # 3. Stop now blocked
        buf3 = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps({"conversationId": "cli-contract-conv"}))), patch("sys.stdout", buf3):
            completion_fence_hook.main()
        out3 = json.loads(buf3.getvalue().strip())
        self.assertEqual(out3.get("decision"), "continue")
        self.assertIn("Verification Required", out3.get("reason", ""))

    def test_subsecond_execution(self):
        """Enforces ADR-015 requirement that hook execution latency is sub-second (<1.0s)."""
        start = time.perf_counter()
        conv_id = "test-perf"
        for _ in range(20):
            record_edit("harness/cli.py", conv_id=conv_id, state_dir=self.state_dir)
            evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
            record_verification(success=True, conv_id=conv_id, state_dir=self.state_dir)

        duration = time.perf_counter() - start
        self.assertLess(
            duration,
            1.0,
            f"Expected 20 state cycles to complete in <1.0s, took {duration:.4f}s",
        )


if __name__ == "__main__":
    unittest.main()
