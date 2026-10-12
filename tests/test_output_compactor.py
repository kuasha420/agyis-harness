#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Test Suite for PSL PostToolUse Output Compactor Hook

Verifies:
1. Small output (<2KB) -> passed unmodified.
2. Large output (>10KB) -> successfully compacted with head (500 chars),
   tail (1,000 chars), and error/diagnostic markers preserved.
3. Failing output (non-zero exit code) -> full error preserved.
4. Edge cases (empty input, invalid JSON, missing fields, non-string outputs).
5. PostToolUse contract compliance (valid JSON `{}` on stdout, exit code 0).
6. State persistence and diagnostic logging in state directory.
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

# Ensure harness is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from harness.hooks.output_compactor_hook import (
    compact_output,
    extract_output_and_status,
    main as compactor_main,
    process_payload,
    MAX_OUTPUT_CHARS,
    HEAD_CHARS,
    TAIL_CHARS,
)
from harness.hooks.exec_wrap import main as exec_wrap_main, run_with_compaction


class TestOutputCompactor(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name)
        self.hook_script = PROJECT_ROOT / "harness" / "hooks" / "output_compactor_hook.py"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_state_dir_resolution_prefers_agyis_over_psl(self):
        """Verifies get_state_dir prefers AGYIS_HARNESS_STATE_DIR over PSL_HARNESS_STATE_DIR."""
        from harness.hooks.output_compactor_hook import get_state_dir
        with tempfile.TemporaryDirectory() as td_agyis, tempfile.TemporaryDirectory() as td_psl:
            with patch.dict(os.environ, {
                "AGYIS_HARNESS_STATE_DIR": td_agyis,
                "PSL_HARNESS_STATE_DIR": td_psl,
            }):
                self.assertEqual(get_state_dir(), Path(td_agyis))

            with patch.dict(os.environ, {
                "PSL_HARNESS_STATE_DIR": td_psl,
            }, clear=False):
                os.environ.pop("AGYIS_HARNESS_STATE_DIR", None)
                self.assertEqual(get_state_dir(), Path(td_psl))

    def test_state_dir_fallback_alignment_across_hooks(self):
        """Verifies that when env vars are unset, all hooks resolve to identical fallback directory."""
        from harness.hooks.output_compactor_hook import get_state_dir as compactor_state_dir
        from harness.hooks.anti_loop_hook import get_state_dir as anti_loop_state_dir
        from harness.hooks.completion_fence_hook import get_state_dir as fence_state_dir
        from harness.utils.state import get_state_dir as canonical_state_dir

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AGYIS_HARNESS_STATE_DIR", None)
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
            d1 = compactor_state_dir()
            d2 = anti_loop_state_dir()
            d3 = fence_state_dir()
            d4 = canonical_state_dir()
            self.assertEqual(d1, d4)
            self.assertEqual(d2, d4)
            self.assertEqual(d3, d4)


    # -------------------------------------------------------------------------
    # 1. Small Output (<2KB) -> Unmodified
    # -------------------------------------------------------------------------
    def test_small_output_unmodified(self) -> None:
        """Outputs strictly <= 2048 characters must pass completely unmodified."""
        # 100 characters
        short_text = "Standard short log output: All 4 tests passed successfully."
        self.assertEqual(compact_output(short_text), short_text)

        # 1,500 characters
        mid_text = "A" * 1500
        self.assertEqual(compact_output(mid_text), mid_text)

        # Boundary: Exactly 2048 characters
        boundary_2048 = "B" * MAX_OUTPUT_CHARS
        self.assertEqual(compact_output(boundary_2048), boundary_2048)

    def test_small_output_payload_processing(self) -> None:
        """Verifies process_payload returns wasCompacted=False for small outputs."""
        small_text = "System check OK. No anomalies detected."
        payload = {
            "conversationId": "test-conv-small",
            "stepIdx": 10,
            "output": small_text,
            "exitCode": 0,
        }
        record = process_payload(payload, state_dir=self.state_dir)
        self.assertFalse(record["wasCompacted"])
        self.assertEqual(record["originalChars"], len(small_text))
        self.assertEqual(record["compactedChars"], len(small_text))
        self.assertEqual(record["savedChars"], 0)
        self.assertEqual(record["compactedOutput"], small_text)

    # -------------------------------------------------------------------------
    # 2. Large Output (>10KB) -> Head, Tail, and Error Markers Preserved
    # -------------------------------------------------------------------------
    def test_large_output_compacted_with_head_tail_and_error_markers(self) -> None:
        """
        Outputs > 10KB must be compacted while strictly preserving:
        - First 500 characters (head)
        - Last 1,000 characters (tail)
        - All lines containing exit code, fatal, error, or failure keywords
        - Compaction marker reporting truncated character count
        """
        # Construct >10KB payload (approx 12KB)
        head_content = "HEAD_START_" + ("H" * 479) + "_HEAD_END_"  # 500 chars
        self.assertEqual(len(head_content), 500)

        tail_content = "_TAIL_START_" + ("T" * 979) + "_TAIL_END"  # 1000 chars
        self.assertEqual(len(tail_content), 1000)

        middle_lines = [
            "Normal trace line: initializing connection pool...",
            "Normal trace line: loading cached fixtures...",
            "[CRITICAL_ERROR] Database connection pool timed out on replica-3",
            "Normal trace line: retrying pool connection...",
            "FATAL: unhandled kernel exception in worker sub-process",
            "Normal trace line: flushing pending telemetry buffers...",
            "Process exited with exit code: 137 (OOM Killer invoked)",
            "Normal trace line: writing crash snapshot...",
            "Detected failure in post-flight validation pipeline",
            "Normal trace line: teardown complete.",
        ]
        # Pad with 10,000 characters of ordinary log noise
        padding_filler = "LOG_FILLER_NOISE: " + ("x" * 80) + "\n"
        middle_noise = padding_filler * 100

        full_middle = "\n".join(middle_lines) + "\n" + middle_noise
        large_output = f"{head_content}\n{full_middle}\n{tail_content}"
        self.assertGreater(len(large_output), 10_000)

        compacted = compact_output(large_output, exit_code=0)

        # 1. Substantially smaller than original
        self.assertLess(len(compacted), len(large_output))

        # 2. First 500 characters strictly preserved
        self.assertTrue(
            compacted.startswith(head_content),
            "Compacted output must start with the exact first 500 characters.",
        )

        # 3. Last 1000 characters strictly preserved
        self.assertTrue(
            compacted.endswith(tail_content),
            "Compacted output must end with the exact last 1000 characters.",
        )

        # 4. Error, fatal, failure, and exit code lines preserved
        self.assertIn("[CRITICAL_ERROR] Database connection pool timed out on replica-3", compacted)
        self.assertIn("FATAL: unhandled kernel exception in worker sub-process", compacted)
        self.assertIn("Process exited with exit code: 137 (OOM Killer invoked)", compacted)
        self.assertIn("Detected failure in post-flight validation pipeline", compacted)

        # 5. Compactor marker present
        self.assertIn("[... PSL Compactor:", compacted)
        self.assertIn("characters truncated", compacted)

        # 6. Non-error middle filler omitted
        self.assertNotIn(middle_noise, compacted)

    def test_large_output_payload_processing_and_savings(self) -> None:
        """Verifies process_payload records accurate metrics for >10KB compaction."""
        head = "H" * HEAD_CHARS
        tail = "T" * TAIL_CHARS
        noise = "N" * 15000
        large_output = head + noise + tail
        self.assertEqual(len(large_output), 16500)

        payload = {
            "conversationId": "test-conv-large",
            "stepIdx": 42,
            "toolCall": {"name": "run_command"},
            "output": large_output,
            "exitCode": 0,
        }
        record = process_payload(payload, state_dir=self.state_dir)
        self.assertTrue(record["wasCompacted"])
        self.assertEqual(record["originalChars"], 16500)
        self.assertGreater(record["savedChars"], 14000)
        self.assertEqual(record["compactedChars"], len(record["compactedOutput"]))

        # Check cached state files
        conv_file = self.state_dir / "compactor_test-conv-large.json"
        last_file = self.state_dir / "last_compaction.json"
        txt_file = self.state_dir / "last_compacted_output.txt"
        log_file = self.state_dir / "compactor_diagnostics.log"

        self.assertTrue(conv_file.exists())
        self.assertTrue(last_file.exists())
        self.assertTrue(txt_file.exists())
        self.assertTrue(log_file.exists())

        saved_data = json.loads(conv_file.read_text(encoding="utf-8"))
        self.assertEqual(saved_data["conversationId"], "test-conv-large")
        self.assertEqual(saved_data["stepIdx"], 42)
        self.assertTrue(saved_data["wasCompacted"])

    # -------------------------------------------------------------------------
    # 3. Failing Output (Non-Zero Exit Code) -> Full Error Preserved
    # -------------------------------------------------------------------------
    def test_failing_output_preserved_full(self) -> None:
        """
        When exit code is non-zero or error status is detected, the entire output
        must be preserved without any compaction or truncation.
        """
        head = "H" * HEAD_CHARS
        tail = "T" * TAIL_CHARS
        noise = "DETAILED_TRACEBACK_LINE_" * 500  # ~12KB
        failing_output = f"{head}\n{noise}\n{tail}"
        self.assertGreater(len(failing_output), 12000)

        # Exit code 1
        res1 = compact_output(failing_output, exit_code=1)
        self.assertEqual(res1, failing_output)

        # Exit code 127 (command not found)
        res127 = compact_output(failing_output, exit_code=127)
        self.assertEqual(res127, failing_output)

        # Exit code 255 (SSH failure)
        res255 = compact_output(failing_output, exit_code=255)
        self.assertEqual(res255, failing_output)

        # is_error flag True
        res_err = compact_output(failing_output, exit_code=0, is_error=True)
        self.assertEqual(res_err, failing_output)

    def test_failing_output_via_payload_variants(self) -> None:
        """Verifies failure detection across different PostToolUse payload formats."""
        large_error = "Traceback (most recent call last):\n" + ("  File 'app.py', line 12\n" * 400)
        self.assertGreater(len(large_error), 10000)

        # 1. Payload with explicit error string
        p1 = {"output": large_error, "error": "exit status 1"}
        r1 = process_payload(p1, state_dir=self.state_dir)
        self.assertFalse(r1["wasCompacted"])
        self.assertEqual(r1["compactedOutput"], large_error)
        self.assertEqual(r1["exitCode"], 1)

        # 2. Payload with exit_code in arguments
        p2 = {"output": large_error, "exit_code": 2}
        r2 = process_payload(p2, state_dir=self.state_dir)
        self.assertFalse(r2["wasCompacted"])
        self.assertEqual(r2["compactedOutput"], large_error)

        # 3. Payload with status = ERROR
        p3 = {"output": large_error, "status": "ERROR"}
        r3 = process_payload(p3, state_dir=self.state_dir)
        self.assertFalse(r3["wasCompacted"])
        self.assertEqual(r3["compactedOutput"], large_error)

        # 4. Text containing exit code failure pattern
        text_with_exit_code = f"{large_error}\nCommand failed with exit code: 1"
        p4 = {"output": text_with_exit_code}
        r4 = process_payload(p4, state_dir=self.state_dir)
        self.assertFalse(r4["wasCompacted"])
        self.assertEqual(r4["exitCode"], 1)
        self.assertTrue(r4["isError"])

    # -------------------------------------------------------------------------
    # 4. Edge Cases: Empty Input, Invalid JSON, Boundary Lengths
    # -------------------------------------------------------------------------
    def test_edge_cases_empty_and_none(self) -> None:
        """Verifies empty strings and None values produce empty output without errors."""
        self.assertEqual(compact_output(""), "")
        self.assertEqual(compact_output(None), "")

        # Empty payload
        record = process_payload({}, state_dir=self.state_dir)
        self.assertFalse(record["wasCompacted"])
        self.assertEqual(record["compactedOutput"], "")

    def test_edge_case_boundary_2049(self) -> None:
        """An output of 2,049 chars with exit_code=0 is the first length compacted."""
        head = "H" * HEAD_CHARS
        tail = "T" * TAIL_CHARS
        middle = "M" * (2049 - HEAD_CHARS - TAIL_CHARS)
        output_2049 = head + middle + tail
        self.assertEqual(len(output_2049), 2049)

        compacted = compact_output(output_2049, exit_code=0)
        self.assertTrue(compacted.startswith(head))
        self.assertTrue(compacted.endswith(tail))
        self.assertIn("characters truncated", compacted)

    def test_transcript_fallback_lookup(self) -> None:
        """When output is missing from payload, reads step content from transcript file."""
        transcript_file = self.state_dir / "transcript.jsonl"
        large_tool_content = "STEP_HEAD_" + ("Z" * 12000) + "_STEP_TAIL"
        step_payload = {
            "step_index": 7,
            "type": "GENERIC",
            "content": large_tool_content,
        }
        transcript_file.write_text(json.dumps(step_payload) + "\n", encoding="utf-8")

        payload = {
            "conversationId": "test-transcript-fallback",
            "stepIdx": 7,
            "transcriptPath": str(transcript_file),
            "exitCode": 0,
        }
        record = process_payload(payload, state_dir=self.state_dir)
        self.assertTrue(record["wasCompacted"])
        self.assertEqual(record["originalChars"], len(large_tool_content))
        self.assertTrue(record["compactedOutput"].startswith("STEP_HEAD_"))

    # -------------------------------------------------------------------------
    # 5. CLI Subprocess & PostToolUse Contract Compliance
    # -------------------------------------------------------------------------
    def test_cli_post_tool_use_contract_success(self) -> None:
        """PostToolUse contract requires stdout to be exact JSON `{}` and exit 0."""
        payload = json.dumps({
            "conversationId": "cli-test-ok",
            "stepIdx": 1,
            "output": "A" * 15000,
            "exitCode": 0,
        })
        with patch.dict(os.environ, {"PSL_HARNESS_STATE_DIR": str(self.state_dir)}):
            with patch("sys.stdin", io.StringIO(payload)), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                compactor_main()
                self.assertEqual(mock_out.getvalue().strip(), "{}")

    def test_cli_post_tool_use_contract_empty_stdin(self) -> None:
        """Empty stdin must gracefully output `{}` with exit code 0."""
        with patch.dict(os.environ, {"PSL_HARNESS_STATE_DIR": str(self.state_dir)}):
            with patch("sys.stdin", io.StringIO("")), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                compactor_main()
                self.assertEqual(mock_out.getvalue().strip(), "{}")

    def test_cli_post_tool_use_contract_invalid_json(self) -> None:
        """Malformed JSON on stdin must gracefully output `{}` with exit code 0."""
        with patch.dict(os.environ, {"PSL_HARNESS_STATE_DIR": str(self.state_dir)}):
            with patch("sys.stdin", io.StringIO("<<<MALFORMED_JSON_PAYLOAD>>>{")), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                compactor_main()
                self.assertEqual(mock_out.getvalue().strip(), "{}")

    def test_cli_post_tool_use_contract_non_dict_json(self) -> None:
        """Non-dict JSON (e.g. array or primitive) must output `{}` with exit code 0."""
        with patch.dict(os.environ, {"PSL_HARNESS_STATE_DIR": str(self.state_dir)}):
            with patch("sys.stdin", io.StringIO("[1, 2, 3]")), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                compactor_main()
                self.assertEqual(mock_out.getvalue().strip(), "{}")

    # -------------------------------------------------------------------------
    # 6. In-Band Execution Wrapper (exec_wrap.py) Compaction Tests
    # -------------------------------------------------------------------------
    def test_exec_wrap_short_output_verbatim(self) -> None:
        """run_with_compaction emits short output verbatim with exit code 0."""
        cmd = ["echo", "hello from in-band execution"]
        code, out = run_with_compaction(cmd, shell=False)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "hello from in-band execution")

    def test_exec_wrap_large_output_compacted_on_success(self) -> None:
        """run_with_compaction compacts large output on exit code 0."""
        # Generate ~6KB output
        code_script = "print('HEAD_START_' + 'A'*485 + '_HEAD_END'); print('NOISE_'*600); print('TAIL_START_' + 'Z'*985 + '_TAIL_END')"
        cmd = [sys.executable, "-c", code_script]
        code, out = run_with_compaction(cmd, shell=False)
        self.assertEqual(code, 0)
        self.assertLess(len(out), 2048)
        self.assertTrue(out.startswith("HEAD_START_"))
        self.assertTrue(out.endswith("_TAIL_END\n") or out.endswith("_TAIL_END"))
        self.assertIn("[... PSL Compactor:", out)

    def test_exec_wrap_nonzero_exit_preserves_full_output(self) -> None:
        """run_with_compaction preserves full output when exit code != 0."""
        code_script = "import sys; print('CRITICAL_FAILURE_' * 500); sys.exit(7)"
        cmd = [sys.executable, "-c", code_script]
        code, out = run_with_compaction(cmd, shell=False)
        self.assertEqual(code, 7)
        self.assertGreater(len(out), 8000)
        self.assertNotIn("[... PSL Compactor:", out)

    def test_exec_wrap_cli_helper(self) -> None:
        """CLI helper executes command and prints compacted output."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = exec_wrap_main(["-c", "echo cli-wrapper-test"])
            self.assertEqual(code, 0)
            self.assertEqual(mock_out.getvalue().strip(), "cli-wrapper-test")

    def test_exec_wrap_sequence_shell_true_escapes_spaces(self) -> None:
        """run_with_compaction uses shlex.join for sequence arguments with shell=True (DEFECT-L3-03)."""
        cmd = ["sh", "-c", 'echo "$@"', "sh", "argument with spaces"]
        code, out = run_with_compaction(cmd, shell=True)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "argument with spaces")

    def test_exec_wrap_hermetic_sys_path(self) -> None:
        """
        Verifies exec_wrap.py dynamically injects repo root into sys.path when
        invoked out-of-band without PYTHONPATH and from an arbitrary working directory.
        """
        clean_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PSL_HARNESS_STATE_DIR": str(self.state_dir),
        }
        clean_env.pop("PYTHONPATH", None)

        script_path = PROJECT_ROOT / "harness" / "hooks" / "exec_wrap.py"
        cmd = [sys.executable, str(script_path), "-c", "echo exec_wrap_standalone_ok"]
        proc = subprocess.run(
            cmd,
            cwd=str(self.state_dir),
            env=clean_env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"exec_wrap.py failed when executed without PYTHONPATH:\nStderr: {proc.stderr}\nStdout: {proc.stdout}",
        )
        self.assertEqual(proc.stdout.strip(), "exec_wrap_standalone_ok")
        self.assertNotIn("ModuleNotFoundError", proc.stderr)


if __name__ == "__main__":
    unittest.main()
