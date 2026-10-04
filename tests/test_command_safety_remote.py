#!/usr/bin/env python3
"""
Hermetic unit tests for remote SSH inspection and sanitization in command_safety_hook.py (ADR-027).
"""

import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from harness.hooks.command_safety_hook import (
    ensure_ssh_socket_dir,
    inject_ssh_timeouts,
    sanitize_command,
    sanitize_ssh_remote_payload,
)


class TestCommandSafetyRemote(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orig_state_dir = os.environ.get("PSL_HARNESS_STATE_DIR")
        os.environ["PSL_HARNESS_STATE_DIR"] = self.temp_dir.name

    def tearDown(self):
        if self.orig_state_dir is not None:
            os.environ["PSL_HARNESS_STATE_DIR"] = self.orig_state_dir
        else:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
        self.temp_dir.cleanup()

    def test_ensure_ssh_socket_dir_permissions(self):
        """Verifies that the socket directory is created with 0700 permissions."""
        sock_dir = ensure_ssh_socket_dir()
        self.assertTrue(sock_dir.exists())
        self.assertTrue(sock_dir.is_dir())
        mode = stat.S_IMODE(sock_dir.stat().st_mode)
        self.assertEqual(mode, 0o700)

    def test_ssh_multiplexing_options_injected(self):
        """Verifies OpenSSH ControlMaster multiplexing options are injected."""
        cmd = "ssh user@host"
        mod, changed = inject_ssh_timeouts(cmd)
        self.assertTrue(changed)
        self.assertIn("-o ControlMaster=auto", mod)
        self.assertIn("-o ControlPath=~/.cache/psl/ssh/cm_%C", mod)
        self.assertIn("-o ControlPersist=10m", mod)
        self.assertIn("-o BatchMode=yes", mod)
        self.assertIn("-o ConnectTimeout=10", mod)
        self.assertIn("-o ServerAliveInterval=15", mod)

    def test_remote_grep_sanitization(self):
        """Verifies remote grep/diff/pgrep pattern probes get || [ $? -eq 1 ]."""
        cases = [
            (
                'ssh host "grep foo file.txt"',
                'ssh host "grep foo file.txt || [ \\$? -eq 1 ]"',
            ),
            (
                "ssh host 'grep error log.txt'",
                "ssh host 'grep error log.txt || [ $? -eq 1 ]'",
            ),
            (
                "ssh host grep foo file.txt",
                'ssh host "grep foo file.txt || [ \\$? -eq 1 ]"',
            ),
            (
                'ssh host "diff -u a.txt b.txt"',
                'ssh host "diff -u a.txt b.txt || [ \\$? -eq 1 ]"',
            ),
            (
                'ssh host "pgrep node"',
                'ssh host "pgrep node || [ \\$? -eq 1 ]"',
            ),
        ]
        for raw, expected in cases:
            mod, changed, reasons = sanitize_ssh_remote_payload(raw)
            self.assertTrue(changed, f"Failed on {raw}")
            self.assertEqual(mod, expected)
            self.assertIn("sanitized remote pattern search against benign Exit Code 1", reasons)

    def test_remote_grep_already_sanitized(self):
        """Verifies grep commands already guarded are untouched."""
        already_safe = [
            'ssh host "grep foo file.txt || [ $? -eq 1 ]"',
            'ssh host "grep foo file.txt || true"',
            'ssh host "grep foo file.txt || :"',
        ]
        for cmd in already_safe:
            mod, changed, reasons = sanitize_ssh_remote_payload(cmd)
            self.assertFalse(changed)
            self.assertEqual(mod, cmd)
            self.assertEqual(reasons, [])

    def test_remote_toolchain_login_shell_promotion(self):
        """Verifies toolchain binaries (pm2, node, pnpm, cargo, nvm, uv) get bash -l -c."""
        cases = [
            (
                'ssh host "pm2 restart app"',
                'ssh host "bash -l -c \'pm2 restart app\'"',
            ),
            (
                "ssh host 'pm2 status'",
                'ssh host "bash -l -c \'pm2 status\'"',
            ),
            (
                "ssh host pm2 list",
                'ssh host "bash -l -c \'pm2 list\'"',
            ),
            (
                'ssh host "node server.js"',
                'ssh host "bash -l -c \'node server.js\'"',
            ),
            (
                'ssh host "pnpm run build"',
                'ssh host "bash -l -c \'pnpm run build\'"',
            ),
            (
                'ssh host "cargo test"',
                'ssh host "bash -l -c \'cargo test\'"',
            ),
            (
                'ssh host "nvm use 20"',
                'ssh host "bash -l -c \'nvm use 20\'"',
            ),
            (
                'ssh host "uv run script.py"',
                'ssh host "bash -l -c \'uv run script.py\'"',
            ),
        ]
        for raw, expected in cases:
            mod, changed, reasons = sanitize_ssh_remote_payload(raw)
            self.assertTrue(changed, f"Failed on {raw}")
            self.assertEqual(mod, expected)
            self.assertIn("wrapped remote command in login shell (bash -l) for toolchain PATH availability", reasons)

    def test_remote_toolchain_already_wrapped_or_path(self):
        """Verifies toolchains already wrapped in login shell or with explicit PATH are untouched."""
        untouched = [
            'ssh host "bash -l -c \'pm2 status\'"',
            'ssh host "bash --login -c \'node app.js\'"',
            'ssh host "PATH=/opt/node/bin:$PATH pm2 list"',
            'ssh host "export PATH=/usr/bin:$PATH; pnpm build"',
        ]
        for cmd in untouched:
            mod, changed, reasons = sanitize_ssh_remote_payload(cmd)
            self.assertFalse(changed, f"Should not modify {cmd}")
            self.assertEqual(mod, cmd)

    def test_remote_toolchain_and_grep_combination(self):
        """Verifies combination of toolchain and pattern probe applies both sanitizations."""
        cmd = 'ssh host "pm2 logs | grep error"'
        mod, changed, reasons = sanitize_ssh_remote_payload(cmd)
        self.assertTrue(changed)
        expected = 'ssh host "bash -l -c \'pm2 logs | grep error || [ \\$? -eq 1 ]\'"'
        self.assertEqual(mod, expected)
        self.assertEqual(len(reasons), 2)
        self.assertIn("sanitized remote pattern search against benign Exit Code 1", reasons)
        self.assertIn("wrapped remote command in login shell (bash -l) for toolchain PATH availability", reasons)

    def test_non_toolchain_commands_untouched(self):
        """Verifies non-toolchain commands (uptime, ls, cat) are not wrapped in bash -l."""
        neutral_cmds = [
            'ssh host uptime',
            'ssh host "ls -la /var/log"',
            'ssh host "cat /etc/hosts"',
            'ssh host "df -h"',
        ]
        for cmd in neutral_cmds:
            mod, changed, reasons = sanitize_ssh_remote_payload(cmd)
            self.assertFalse(changed, f"Should not modify {cmd}")
            self.assertEqual(mod, cmd)

    def test_end_to_end_sanitize_command(self):
        """Verifies end-to-end sanitize_command applies multiplexing + remote payload sanitization."""
        cmd = 'ssh knot-desktop "pm2 list"'
        decision, mod, reason = sanitize_command(cmd)
        self.assertEqual(decision, "allow")
        self.assertIsNotNone(mod)
        self.assertIn("-o ControlMaster=auto", mod)
        self.assertIn("-o ConnectTimeout=10", mod)
        self.assertIn('"bash -l -c \'pm2 list\'"', mod)
        self.assertIn("injected non-blocking SSH timeout", reason)
        self.assertIn("wrapped remote command in login shell", reason)

        # Idempotency check
        decision2, mod2, reason2 = sanitize_command(mod)
        self.assertEqual(decision2, "allow")
        self.assertIsNone(mod2)
        self.assertIsNone(reason2)


if __name__ == "__main__":
    unittest.main()
