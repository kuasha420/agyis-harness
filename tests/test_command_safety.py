#!/usr/bin/env python3
"""
Unit and integration tests for harness/hooks/command_safety_hook.py
"""

import json
from pathlib import Path
import sqlite3
import subprocess
import unittest

from harness.hooks.command_safety_hook import (
    is_inline_python_command,
    sanitize_command,
    should_sanitize_grep_or_diff,
)


class TestCommandSafety(unittest.TestCase):
    def test_dangerous_patterns_blocked(self):
        dangerous = [
            "rm -rf /",
            "rm -rf /*",
            "rm -r -f /",
            "rm -rf ./*",
            "rm -rf *",
            "mkfs /dev/sda1",
            "dd if=/dev/zero of=/dev/sda",
        ]
        for cmd in dangerous:
            decision, mod, reason = sanitize_command(cmd)
            self.assertEqual(decision, "deny", f"Command should be denied: {cmd}")
            self.assertIn("prohibited destructive pattern", reason)

    def test_interactive_commands_blocked(self):
        interactive = [
            "nano file.txt",
            "vim script.py",
            "vi config.yaml",
            "htop",
            "top",
            "less output.log",
        ]
        for cmd in interactive:
            decision, mod, reason = sanitize_command(cmd)
            self.assertEqual(decision, "deny", f"Interactive command should be denied: {cmd}")
            self.assertIn("Interactive command", reason)

    def test_pager_enforcement(self):
        decision, mod, reason = sanitize_command("git diff")
        self.assertEqual(decision, "allow")
        self.assertEqual(mod, "PAGER=cat git diff")

        decision, mod, reason = sanitize_command("git log -n 5")
        self.assertEqual(decision, "allow")
        self.assertEqual(mod, "PAGER=cat git log -n 5")

        # Already non-interactive
        decision, mod, reason = sanitize_command("git --no-pager diff")
        self.assertEqual(decision, "allow")
        self.assertIsNone(mod)

    def test_inline_python_detection(self):
        self.assertTrue(is_inline_python_command('python3 -c "print(1)"'))
        self.assertTrue(is_inline_python_command('python -c "import sys; print(sys.version)"'))
        self.assertFalse(is_inline_python_command('pytest tests/'))
        self.assertFalse(is_inline_python_command('python script.py'))
        self.assertFalse(is_inline_python_command('python3 -m unittest discover'))

    def test_hermetic_python_injection(self):
        decision, mod, reason = sanitize_command('python3 -c "data = {}; print(f\\\"{data.get(\'k\')}\\\")"')
        self.assertEqual(decision, "allow")
        self.assertIsNotNone(mod)
        self.assertIn('PATH="', mod)
        self.assertIn("cpython-3.1", mod)
        self.assertIn("python3 -c", mod)

    def test_should_sanitize_grep_or_diff(self):
        # Valid candidates for surgical tail sanitization
        self.assertTrue(should_sanitize_grep_or_diff("grep 'foo' file.txt"))
        self.assertTrue(should_sanitize_grep_or_diff("git diff | grep 'def '"))
        self.assertTrue(should_sanitize_grep_or_diff("diff file1 file2"))
        self.assertTrue(should_sanitize_grep_or_diff("cat log.txt | grep -E 'ERROR|WARN'"))

        # Ineligible (compound conditionals, already guarded, or non-terminal)
        self.assertFalse(should_sanitize_grep_or_diff("if grep -q 'foo' file; then echo yes; fi"))
        self.assertFalse(should_sanitize_grep_or_diff("grep 'foo' file && rm bar"))
        self.assertFalse(should_sanitize_grep_or_diff("grep 'foo' file || exit 1"))
        self.assertFalse(should_sanitize_grep_or_diff("grep 'foo' file || true"))
        self.assertFalse(should_sanitize_grep_or_diff("grep 'foo' file || [ $? -eq 1 ]"))
        self.assertFalse(should_sanitize_grep_or_diff("cat log.txt | grep 'foo' | sort"))

    def test_surgical_grep_tail_rewrite(self):
        decision, mod, reason = sanitize_command("grep -rn 'needle' src/")
        self.assertEqual(decision, "allow")
        self.assertEqual(mod, "grep -rn 'needle' src/ || [ $? -eq 1 ]")

        decision, mod, reason = sanitize_command("git diff | grep 'class '")
        self.assertEqual(decision, "allow")
        self.assertEqual(mod, "PAGER=cat git diff | grep 'class ' || [ $? -eq 1 ]")

    def test_historical_fstring_failures_replay(self):
        """
        Replays exact failing command lines from telemetry.db (session 270b7abc)
        under the sanitized command to verify they now succeed with exit code 0.
        """
        db_path = Path(__file__).parent.parent / "data/telemetry.db"
        if not db_path.exists():
            self.skipTest("telemetry.db not present")

        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("""
            SELECT command_line FROM tool_calls 
            WHERE session_id = '270b7abc-9b59-4f50-9c49-de3ed7e04f06' AND step_index IN (176, 182)
        """)
        rows = c.fetchall()
        conn.close()

        for (raw_cmd,) in rows:
            cmd = json.loads(raw_cmd) if raw_cmd.startswith('"') else raw_cmd
            decision, mod_cmd, reason = sanitize_command(cmd)
            self.assertEqual(decision, "allow")
            self.assertIsNotNone(mod_cmd)

            proc = subprocess.run(
                mod_cmd,
                shell=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                proc.returncode, 0,
                f"Historical failing script failed under sanitized command: {proc.stderr}"
            )


if __name__ == "__main__":
    unittest.main()
