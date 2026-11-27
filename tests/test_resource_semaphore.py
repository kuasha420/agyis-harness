#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Hermetic unit and cross-worktree serialization tests for Issue #67 Resource Semaphore."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from harness.hooks import anti_drift_hook, command_safety_hook, completion_fence_hook
from harness.hooks.resource_semaphore import (
    MATRIX_JSON_PATH,
    check_memory_guard,
    evaluate_resource_semaphore,
    get_available_ram_mb,
    get_min_free_ram_mb,
    get_semaphore_wait_seconds,
    is_heavy_verification_command,
    resolve_semaphore_lock_path,
    wrap_with_concurrency_semaphore,
)


def _invoke_hook_main(hook_mod, payload: dict) -> dict:
    stdout_buf = io.StringIO()
    with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", stdout_buf):
        hook_mod.main()
    return json.loads(stdout_buf.getvalue().strip())


class TestMatrixThresholdsAndClassifier(unittest.TestCase):
    """Validates matrix.json threshold configuration and heavy/lightweight command classification."""

    def test_matrix_json_contains_system_thresholds_and_env_override(self) -> None:
        raw = json.loads(MATRIX_JSON_PATH.read_text(encoding="utf-8"))
        self.assertIn("system_thresholds", raw)
        self.assertEqual(raw["system_thresholds"]["min_free_ram_mb"], 1536)
        self.assertEqual(raw["system_thresholds"]["semaphore_wait_seconds"], 300)

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AGYIS_MIN_FREE_RAM_MB", None)
            os.environ.pop("AGYIS_SEMAPHORE_WAIT_SECONDS", None)
            self.assertEqual(get_min_free_ram_mb(), 1536)
            self.assertEqual(get_semaphore_wait_seconds(), 300)

        with patch.dict(os.environ, {"AGYIS_MIN_FREE_RAM_MB": "2048", "AGYIS_SEMAPHORE_WAIT_SECONDS": "45"}):
            self.assertEqual(get_min_free_ram_mb(), 2048)
            self.assertEqual(get_semaphore_wait_seconds(), 45)

    def test_heavy_verification_commands_detected(self) -> None:
        heavy_cmds = [
            "npx playwright test",
            "pnpm exec puppeteer run",
            "cypress run --headless",
            "vitest run --browser",
            "npm run test:e2e",
            "pnpm run vrt",
            "cargo build --all-targets",
            "docker run --rm alpine true",
            "pnpm next build",
            "cd /tmp && npx playwright test tests/smoke.spec.ts",
            "python3 -m pytest --browser chromium",
        ]
        for cmd in heavy_cmds:
            with self.subTest(cmd=cmd):
                self.assertTrue(is_heavy_verification_command(cmd))

    def test_lightweight_unit_tests_and_quoted_literals_bypassed(self) -> None:
        light_cmds = [
            "python3 -m unittest tests/test_anti_clobber.py",
            "python3 -m unittest tests/e2e/test_foo.py",
            "python3 -m unittest tests/playwright/test_foo.py",
            "python3 -m unittest -k e2e",
            "python3 -m harness.cli doctor --e2e",
            "python3 -m pytest tests/test_unit.py",
            "pytest tests/test_unit.py",
            "cargo test my_single_unit",
            "agyis audit aff",
            "agyis doctor",
            "agyis status",
            "python3 -m harness.cli audit aff",
            'echo "npx playwright test && next build"',
            'rg "docker run" harness/',
            'grep "playwright" README.md',
            'git commit -m "fix playwright and next build memory guard"',
            "npx playwright --version",
        ]
        for cmd in light_cmds:
            with self.subTest(cmd=cmd):
                self.assertFalse(is_heavy_verification_command(cmd))


class TestMemoryGuard(unittest.TestCase):
    """Validates zero-dep /proc/meminfo MemAvailable probing and fail-open behavior."""

    def test_denies_heavy_command_when_memavailable_below_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meminfo = Path(tmp) / "meminfo"
            meminfo.write_text("MemTotal:       16384000 kB\nMemAvailable:    1048576 kB\n", encoding="utf-8")
            self.assertEqual(get_available_ram_mb(meminfo), 1024)

            res = check_memory_guard("npx playwright test", meminfo_path=meminfo, min_free_ram_mb=1536)
            self.assertIsNotNone(res)
            self.assertEqual(res["decision"], "deny")
            self.assertIn("[PSL Memory Guard]", res["reason"])
            self.assertIn("1024 MB < 1536 MB", res["reason"])

            # Lightweight unit test passes even under low RAM
            self.assertIsNone(check_memory_guard("python3 -m unittest tests/test_a.py", meminfo_path=meminfo, min_free_ram_mb=1536))

    def test_allows_when_ram_sufficient_or_meminfo_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meminfo = Path(tmp) / "meminfo"
            meminfo.write_text("MemTotal:       16384000 kB\nMemAvailable:    4194304 kB\n", encoding="utf-8")
            self.assertEqual(get_available_ram_mb(meminfo), 4096)
            self.assertIsNone(check_memory_guard("npx playwright test", meminfo_path=meminfo, min_free_ram_mb=1536))

            missing = Path(tmp) / "nonexistent_meminfo"
            self.assertIsNone(get_available_ram_mb(missing))
            self.assertIsNone(check_memory_guard("npx playwright test", meminfo_path=missing, min_free_ram_mb=1536))


class TestCrossWorktreeConcurrencySemaphore(unittest.TestCase):
    """Validates flock/Python command wrapping, idempotency, and real cross-worktree serialization."""

    def test_wrap_flock_python_fallback_and_idempotency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            ws = Path(tmp) / "repo"
            ws.mkdir()

            wrapped_flock, did_wrap = wrap_with_concurrency_semaphore(
                "npx playwright test", workspace_dir=ws, state_dir=state_dir, wait_seconds=12, flock_binary="/usr/bin/flock",
            )
            self.assertTrue(did_wrap)
            self.assertIn("AGYIS_SEMAPHORE_LOCKED=1", wrapped_flock)
            self.assertIn("flock -w 12", wrapped_flock)
            self.assertIn("bash -c", wrapped_flock)

            # Idempotent on already-wrapped commands
            again, did_wrap_again = wrap_with_concurrency_semaphore(wrapped_flock, workspace_dir=ws, state_dir=state_dir)
            self.assertFalse(did_wrap_again)
            self.assertEqual(again, wrapped_flock)

            # Portable Python fallback when flock is unavailable
            wrapped_py, did_py = wrap_with_concurrency_semaphore(
                "next build", workspace_dir=ws, state_dir=state_dir, wait_seconds=15, flock_binary="",
            )
            self.assertTrue(did_py)
            self.assertIn("harness.hooks.resource_semaphore", wrapped_py)
            self.assertIn("--wait 15", wrapped_py)

            # Idempotent when env guard is set
            with patch.dict(os.environ, {"AGYIS_SEMAPHORE_LOCKED": "1"}):
                unchanged, did_env = wrap_with_concurrency_semaphore("next build", workspace_dir=ws, state_dir=state_dir)
                self.assertFalse(did_env)
                self.assertEqual(unchanged, "next build")

    def test_real_two_process_serialization_across_git_worktrees_zero_repo_dirt(self) -> None:
        git_bin = shutil.which("git")
        if not git_bin:
            self.skipTest("git binary not available")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main_repo = root / "main_repo"
            wt_repo = root / "worktree_b"
            state_dir = root / "state"
            event_log = root / "events.log"
            main_repo.mkdir()

            env = {
                **os.environ,
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@example.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@example.com",
            }
            subprocess.run([git_bin, "init", "-q"], cwd=main_repo, env=env, check=True)
            (main_repo / "README.md").write_text("# Test\n", encoding="utf-8")
            subprocess.run([git_bin, "add", "README.md"], cwd=main_repo, env=env, check=True)
            subprocess.run([git_bin, "commit", "-q", "-m", "init"], cwd=main_repo, env=env, check=True)
            subprocess.run([git_bin, "worktree", "add", "-q", "-b", "wt-b", str(wt_repo)], cwd=main_repo, env=env, check=True)

            # Both worktrees MUST resolve to the exact same lockfile inside state_dir
            lock_main = resolve_semaphore_lock_path(workspace_dir=main_repo, state_dir=state_dir)
            lock_wt = resolve_semaphore_lock_path(workspace_dir=wt_repo, state_dir=state_dir)
            self.assertEqual(lock_main, lock_wt)
            self.assertEqual(lock_main.parent.resolve(), state_dir.resolve())

            # Run two real child processes concurrently via the portable Python CLI runner
            # verifying strict non-overlapping critical sections + exact exit code forwarding
            py_exe = sys.executable
            repo_root = str(Path(__file__).resolve().parent.parent)
            child_env = {**os.environ, "PYTHONPATH": repo_root}
            cmd_a = (
                f'{py_exe} -c "import time; '
                f'open({str(event_log)!r}, \'a\').write(\'A_START\\n\'); '
                f'time.sleep(0.12); '
                f'open({str(event_log)!r}, \'a\').write(\'A_END\\n\')"'
            )
            cmd_b = (
                f'{py_exe} -c "import sys; '
                f'open({str(event_log)!r}, \'a\').write(\'B_START\\n\'); '
                f'open({str(event_log)!r}, \'a\').write(\'B_END\\n\'); '
                f'sys.exit(42)"'
            )

            proc_a = subprocess.Popen(
                [py_exe, "-m", "harness.hooks.resource_semaphore", "--lock", str(lock_main), "--wait", "5", "--cmd", cmd_a],
                env=child_env,
            )
            proc_b = subprocess.Popen(
                [py_exe, "-m", "harness.hooks.resource_semaphore", "--lock", str(lock_wt), "--wait", "5", "--cmd", cmd_b],
                env=child_env,
            )
            rc_a = proc_a.wait(timeout=5)
            rc_b = proc_b.wait(timeout=5)

            self.assertEqual(rc_a, 0)
            self.assertEqual(rc_b, 42)

            events = event_log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(events), 4)
            # Critical sections must NOT interleave: either [A_START, A_END, B_START, B_END] or [B_START, B_END, A_START, A_END]
            self.assertIn(events, [["A_START", "A_END", "B_START", "B_END"], ["B_START", "B_END", "A_START", "A_END"]])

            # Zero untracked files left inside either git worktree
            for repo_dir in (main_repo, wt_repo):
                status = subprocess.run(
                    [git_bin, "status", "--porcelain"], cwd=repo_dir, capture_output=True, text=True, check=True,
                )
                self.assertEqual(status.stdout.strip(), "")


class TestResourceSemaphoreHookIntegration(unittest.TestCase):
    """End-to-end PreToolUse hook wiring for Issue #67 memory guard & semaphore overwrite."""

    def test_anti_drift_and_completion_fence_enforce_memory_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            meminfo = Path(tmp) / "meminfo"
            meminfo.write_text("MemTotal:       16384000 kB\nMemAvailable:     524288 kB\n", encoding="utf-8")
            payload = {
                "hookEventName": "PreToolUse",
                "conversationId": "conv-mem-guard",
                "workspacePaths": [tmp],
                "state_dir": str(state_dir),
                "toolCall": {"name": "run_command", "args": {"CommandLine": "npx playwright test"}},
            }
            with patch("harness.hooks.resource_semaphore.DEFAULT_MEMINFO_PATH", meminfo):
                out = _invoke_hook_main(anti_drift_hook, payload)
                self.assertEqual(out["decision"], "deny")
                self.assertIn("[PSL Memory Guard]", out["reason"])
                self.assertIn("512 MB < 1536 MB", out["reason"])

                denied = completion_fence_hook._is_pre_tool_denied_by_guards(
                    "run_command", payload["toolCall"]["args"], payload, cwd=tmp,
                )
                self.assertTrue(denied)

    def test_command_safety_hook_wraps_heavy_command_and_denies_low_ram(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            lock_file = state_dir / "test.lock"
            high_mem = Path(tmp) / "meminfo_high"
            low_mem = Path(tmp) / "meminfo_low"
            high_mem.write_text("MemTotal:       16384000 kB\nMemAvailable:    8388608 kB\n", encoding="utf-8")
            low_mem.write_text("MemTotal:       16384000 kB\nMemAvailable:     262144 kB\n", encoding="utf-8")

            payload = {
                "workspacePaths": [tmp],
                "toolCall": {"name": "run_command", "args": {"CommandLine": "npx playwright test"}},
            }
            with patch("harness.hooks.resource_semaphore.DEFAULT_MEMINFO_PATH", high_mem), patch.dict(
                os.environ, {"AGYIS_SEMAPHORE_LOCK_FILE": str(lock_file)},
            ):
                out = _invoke_hook_main(command_safety_hook, payload)
                self.assertEqual(out["decision"], "allow")
                self.assertIn("overwrite", out)
                cmd_out = out["overwrite"]["CommandLine"]
                self.assertIn("AGYIS_SEMAPHORE_LOCKED=1", cmd_out)
                self.assertIn(str(lock_file), cmd_out)

            with patch("harness.hooks.resource_semaphore.DEFAULT_MEMINFO_PATH", low_mem):
                denied_out = _invoke_hook_main(command_safety_hook, payload)
                self.assertEqual(denied_out["decision"], "deny")
                self.assertIn("[PSL Memory Guard]", denied_out["reason"])
                self.assertIn("256 MB < 1536 MB", denied_out["reason"])


if __name__ == "__main__":
    unittest.main()
