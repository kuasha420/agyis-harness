#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Unit Tests for harness/utils/state.py (Phase 1 Remediation: PSL-SPEC-2026-DRA-001).

Validates:
1. State directory defaults to /tmp/agyis_harness_state_{uid} using os.getuid().
2. Respects AGYIS_HARNESS_STATE_DIR and PSL_HARNESS_STATE_DIR overrides.
3. Resilient to mkdir OSError without crashing.
4. Atomic file writes and concurrent history persistence (NamedTemporaryFile + os.replace).
"""

from __future__ import annotations

import concurrent.futures
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from harness.utils.state import (
    atomic_write_json,
    atomic_write_text,
    get_state_dir,
    load_history,
    save_history,
)


class TestStateInfrastructure(unittest.TestCase):
    """Hermetic unit tests for state directory isolation and atomic persistence."""

    def test_default_state_dir_includes_uid(self):
        """Verifies state directory defaults to /tmp/agyis_harness_state_{uid}."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure AGYIS_HARNESS_STATE_DIR and PSL_HARNESS_STATE_DIR are cleared
            os.environ.pop("AGYIS_HARNESS_STATE_DIR", None)
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
            state_dir = get_state_dir()
            uid = os.getuid() if hasattr(os, "getuid") else 0
            expected = Path(f"/tmp/agyis_harness_state_{uid}")
            self.assertEqual(state_dir, expected)

    def test_env_var_overrides(self):
        """Verifies AGYIS_HARNESS_STATE_DIR and PSL_HARNESS_STATE_DIR overrides."""
        with tempfile.TemporaryDirectory() as td_agyis, tempfile.TemporaryDirectory() as td_psl:
            # AGYIS_HARNESS_STATE_DIR has priority
            with patch.dict(os.environ, {"AGYIS_HARNESS_STATE_DIR": td_agyis, "PSL_HARNESS_STATE_DIR": td_psl}):
                self.assertEqual(get_state_dir(), Path(td_agyis))

            # PSL_HARNESS_STATE_DIR fallback
            with patch.dict(os.environ, {"AGYIS_HARNESS_STATE_DIR": "", "PSL_HARNESS_STATE_DIR": td_psl}):
                self.assertEqual(get_state_dir(), Path(td_psl))

    def test_mkdir_oserror_handled_gracefully(self):
        """Verifies that OSError during mkdir does not crash get_state_dir()."""
        with patch("pathlib.Path.mkdir", side_effect=OSError("Read-only file system")):
            with tempfile.TemporaryDirectory() as td:
                with patch.dict(os.environ, {"PSL_HARNESS_STATE_DIR": td}):
                    res = get_state_dir()
                    self.assertEqual(res, Path(td))

    def test_atomic_write_text_and_json(self):
        """Verifies atomic_write_text and atomic_write_json replace files cleanly."""
        with tempfile.TemporaryDirectory() as td:
            target_file = Path(td) / "test.json"
            data = {"status": "ok", "count": 42}
            atomic_write_json(target_file, data, indent=2)

            self.assertTrue(target_file.exists())
            loaded = json.loads(target_file.read_text(encoding="utf-8"))
            self.assertEqual(loaded, data)

            # Overwrite atomically
            new_data = {"status": "updated", "count": 100}
            atomic_write_json(target_file, new_data)
            loaded_new = json.loads(target_file.read_text(encoding="utf-8"))
            self.assertEqual(loaded_new, new_data)

    def test_save_and_load_history(self):
        """Verifies session history persistence and recovery."""
        with tempfile.TemporaryDirectory() as td:
            target_dir = Path(td)
            conv_id = "test-conv-1234"
            history_data = [
                {"tool": "run_command", "args": {"CommandLine": "pwd"}},
                {"tool": "run_command", "args": {"CommandLine": "git status"}},
            ]

            saved_path = save_history(conv_id, history_data, target_dir=target_dir)
            self.assertTrue(saved_path.exists())
            self.assertEqual(saved_path.name, f"history_{conv_id}.json")

            loaded = load_history(conv_id, target_dir=target_dir)
            self.assertEqual(loaded, history_data)

    def test_load_history_corrupted_json_recovery(self):
        """Verifies load_history returns [] on corrupted JSON rather than throwing."""
        with tempfile.TemporaryDirectory() as td:
            target_dir = Path(td)
            conv_id = "corrupt-conv"
            corrupt_file = target_dir / f"history_{conv_id}.json"
            corrupt_file.write_text("NOT_VALID_JSON{{{", encoding="utf-8")

            loaded = load_history(conv_id, target_dir=target_dir)
            self.assertEqual(loaded, [])

    def test_concurrent_atomic_writes(self):
        """Verifies that concurrent atomic writes do not corrupt the JSON file."""
        with tempfile.TemporaryDirectory() as td:
            target_dir = Path(td)
            conv_id = "concurrent-conv"

            def writer(thread_id: int):
                for i in range(20):
                    data = [{"thread": thread_id, "step": i, "payload": "x" * 100}]
                    save_history(conv_id, data, target_dir=target_dir)

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(writer, tid) for tid in range(5)]
                for f in concurrent.futures.as_completed(futures):
                    f.result()

            # The final file must be valid JSON parseable without error
            loaded = load_history(conv_id, target_dir=target_dir)
            self.assertIsInstance(loaded, list)
            self.assertEqual(len(loaded), 1)
            self.assertIn("thread", loaded[0])


if __name__ == "__main__":
    unittest.main()
