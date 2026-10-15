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


if __name__ == "__main__":
    unittest.main()
