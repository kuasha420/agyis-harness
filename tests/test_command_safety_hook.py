#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Unit Tests for command_safety_hook (Phase 1 Remediation: PSL-SPEC-2026-DRA-001).

Validates:
1. Double quotes in commands and f-strings are preserved without corruption or stripping.
2. Grep commands do not receive automatic `|| [ $? -eq 1 ]` tail rewrite.
3. PreToolUse hook JSON interface execution via main().
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from harness.hooks.command_safety_hook import (
    main as safety_main,
    sanitize_command,
    should_sanitize_grep_or_diff,
)


class TestCommandSafetyHookPhase1(unittest.TestCase):
    """Targeted verification for Phase 1 command safety hook fixes."""

    def test_double_quotes_and_fstrings_preserved_without_corruption(self):
        """Asserts bash commands containing double quotes inside expressions pass without syntax corruption."""
        commands = [
            'python3 -c "print(\'hello\')"',
            'python3 -c "import sys; print(f\\\"{sys.version}\\\")"',
            'python3 -c "data = {\'key\': \'val\'}; print(f\\\"{data.get(\'key\')}\\\")"',
            'python3 -c "msg = \\\"hello world\\\"; print(msg)"',
            'python3 -c "import os; print(f\\\"{os.environ.get(\'HOME\')}\\\")"',
        ]
        for cmd in commands:
            decision, mod_cmd, reason = sanitize_command(cmd)
            self.assertEqual(decision, "allow")
            effective_cmd = mod_cmd if mod_cmd is not None else cmd
            # Command must contain the exact payload without stripped or altered quotes
            self.assertIn(cmd, effective_cmd)
            # Ensure no backslash-quote stripping caused corruption
            self.assertNotIn('\\"', effective_cmd.replace(cmd, ""))

    def test_grep_commands_do_not_get_automatic_tail_rewrite(self):
        """Asserts that grep commands are not automatically rewritten with || [ $? -eq 1 ]."""
        grep_commands = [
            "grep -rn 'needle' src/",
            "grep 'TODO' README.md",
            "git diff | grep 'class '",
            "cat output.log | grep -E 'ERROR|WARN'",
            "diff file1.txt file2.txt",
        ]
        for cmd in grep_commands:
            decision, mod_cmd, reason = sanitize_command(cmd)
            self.assertEqual(decision, "allow")
            if mod_cmd is not None:
                # If command is modified (e.g. PAGER=cat for git), it must NOT append the grep tail
                self.assertNotIn("|| [ $? -eq 1 ]", mod_cmd)
                self.assertNotIn("|| [ \\$? -eq 1 ]", mod_cmd)
            else:
                self.assertIsNone(mod_cmd)

    def test_hook_main_json_preserves_quotes_and_does_not_mutate_grep(self):
        """Asserts end-to-end stdin/stdout hook main() contract."""
        # 1. Grep command should allow without CommandLine overwrite
        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "grep -rn 'foo' ."},
            }
        }
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            safety_main()
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")
            self.assertNotIn("overwrite", res)

        # 2. Python inline script with double quotes should preserve quotes
        py_payload = {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": 'python3 -c "print(\'hello\')"' },
            }
        }
        with patch("sys.stdin", io.StringIO(json.dumps(py_payload))), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            safety_main()
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")
            if "overwrite" in res:
                overwritten_cmd = res["overwrite"]["CommandLine"]
                self.assertIn('python3 -c "print(\'hello\')"', overwritten_cmd)


class TestCommandSafetyReaHarmonization(unittest.TestCase):
    """Hermetic unit tests validating REA toolchain & disassembler batch harmonization (Milestone 4)."""

    def test_user_toolchains_includes_rea(self):
        """USER_TOOLCHAINS includes rea."""
        from harness.hooks.command_safety_hook import USER_TOOLCHAINS
        self.assertIn("rea", USER_TOOLCHAINS)

    def test_rea_path_shim_injection(self):
        """rea commands receive user path shims."""
        from harness.hooks.command_safety_hook import inject_path_shims
        with patch("harness.hooks.command_safety_hook.get_user_path_shims", return_value=["/home/user/.npm-global/bin", "/home/user/.local/bin"]):
            mod, changed = inject_path_shims("rea verify-reconstruction")
            self.assertTrue(changed)
            self.assertIn('export PATH="/home/user/.npm-global/bin:/home/user/.local/bin:$PATH"; rea verify-reconstruction', mod)

    def test_command_wrapper_prefix_triggers_shim_injection(self):
        """Wrappers like 'command rea' or 'command -v rea' match USER_TOOLCHAIN_REGEX."""
        from harness.hooks.command_safety_hook import USER_TOOLCHAIN_REGEX, extract_command_binary
        self.assertIsNotNone(USER_TOOLCHAIN_REGEX.search("command rea verify"))
        self.assertIsNotNone(USER_TOOLCHAIN_REGEX.search("command -v rea"))
        self.assertEqual(extract_command_binary("command rea verify"), "rea")
        self.assertEqual(extract_command_binary("command -v rea"), "rea")

    def test_rea_preflight_package_suggestion(self):
        """Preflight tool check emits actionable suggestion for missing rea."""
        from harness.hooks.command_safety_hook import check_preflight_tool_availability
        with patch("shutil.which", return_value=None), patch("harness.hooks.command_safety_hook.get_user_path_shims", return_value=[]):
            res = check_preflight_tool_availability("rea verify")
            self.assertFalse(res["available"])
            self.assertEqual(res["binary"], "rea")
            self.assertIn("pnpm add -g rea-agents", res["suggestion"])

    def test_disassembler_batch_mode_gdb_rewrite(self):
        """Raw gdb commands are automatically rewritten to include -batch."""
        decision, mod_cmd, reason = sanitize_command("gdb /usr/bin/ls")
        self.assertEqual(decision, "allow")
        self.assertIsNotNone(mod_cmd)
        self.assertIn("gdb -batch /usr/bin/ls", mod_cmd)
        self.assertIn("enforced non-interactive gdb -batch mode", reason)

        # Idempotent if -batch already present
        decision, mod_cmd2, reason2 = sanitize_command("gdb -batch /usr/bin/ls")
        self.assertEqual(decision, "allow")
        self.assertIsNone(mod_cmd2)

    def test_disassembler_batch_mode_rizin_rewrite(self):
        """Raw rizin commands are automatically rewritten to include -q."""
        decision, mod_cmd, reason = sanitize_command("rizin -c 'pdf @main' /usr/bin/ls")
        self.assertEqual(decision, "allow")
        self.assertIsNotNone(mod_cmd)
        self.assertIn("rizin -q -c 'pdf @main' /usr/bin/ls", mod_cmd)
        self.assertIn("enforced non-interactive rizin -q batch mode", reason)

        # Idempotent if -q already present
        decision, mod_cmd2, reason2 = sanitize_command("rizin -q -c 'pdf @main' /usr/bin/ls")
        self.assertEqual(decision, "allow")
        self.assertIsNone(mod_cmd2)


if __name__ == "__main__":
    unittest.main()
