#!/usr/bin/env python3
"""
Unit and integration tests for harness/hooks/command_safety_hook.py
"""

import json
from pathlib import Path
import sqlite3
import subprocess
import unittest

from unittest.mock import patch

from harness.hooks.command_safety_hook import (
    SSH_PATTERN,
    get_user_path_shims,
    inject_path_shims,
    inject_ssh_timeouts,
    is_inline_python_command,
    sanitize_command,
    sanitize_ssh_remote_payload,
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

    def test_get_user_path_shims(self):
        shims = get_user_path_shims()
        self.assertIsInstance(shims, list)
        for s in shims:
            self.assertTrue(Path(s).is_dir())

        # Test discovery with mocked directories
        with patch("pathlib.Path.is_dir") as mock_is_dir:
            # All 4 candidate dirs exist
            mock_is_dir.return_value = True
            mocked_shims = get_user_path_shims()
            self.assertEqual(len(mocked_shims), 4)
            self.assertTrue(any(".local/bin" in s for s in mocked_shims))
            self.assertTrue(any(".cargo/bin" in s for s in mocked_shims))
            self.assertTrue(any(".local/share/pnpm" in s for s in mocked_shims))
            self.assertTrue(any(".pyenv/shims" in s for s in mocked_shims))

    def test_user_path_shim_injection(self):
        # Candidate toolchains
        for tool in ("pnpm test", "uv run pytest", "cargo build --release", "pytest tests/"):
            mod, changed = inject_path_shims(tool)
            self.assertTrue(changed, f"Expected injection for: {tool}")
            self.assertTrue(mod.startswith('export PATH="'), f"Expected PATH export for: {tool}")
            self.assertIn(f':$PATH"; {tool}', mod)

            decision, mod_cmd, reason = sanitize_command(tool)
            self.assertEqual(decision, "allow")
            self.assertIsNotNone(mod_cmd)
            self.assertIn("injected user-space toolchain PATH shims", reason)

        # Non-toolchain commands should not trigger injection
        non_tools = ["ls -la", "echo 'hello'", "python script.py", "cat README.md"]
        for cmd in non_tools:
            mod, changed = inject_path_shims(cmd)
            self.assertFalse(changed, f"Should not inject for: {cmd}")
            self.assertEqual(mod, cmd)

        # Already configured PATH should be ignored
        already_configured = [
            'export PATH="/custom/bin:$PATH"; pnpm test',
            'PATH=/usr/bin cargo build',
        ]
        for cmd in already_configured:
            mod, changed = inject_path_shims(cmd)
            self.assertFalse(changed, f"Should not inject when PATH already present: {cmd}")
            self.assertEqual(mod, cmd)

        # Existing candidate path in command should not re-inject
        with_candidate = "~/.local/bin/uv run pytest"
        mod, changed = inject_path_shims(with_candidate)
        self.assertFalse(changed)
        self.assertEqual(mod, with_candidate)

    def test_psl_subcommands_trigger_path_shims(self):
        """Asserts that invoking `psl test` or `psl doctor` triggers inject_path_shims (USER_TOOLCHAINS)."""
        for cmd in ("psl test", "psl doctor"):
            mod, changed = inject_path_shims(cmd)
            self.assertTrue(changed, f"Expected injection for: {cmd}")
            self.assertTrue(mod.startswith('export PATH="'), f"Expected PATH export for: {cmd}")
            self.assertIn(f':$PATH"; {cmd}', mod)

            decision, mod_cmd, reason = sanitize_command(cmd)
            self.assertEqual(decision, "allow")
            self.assertIsNotNone(mod_cmd)
            self.assertIn("injected user-space toolchain PATH shims", reason)

    def test_ssh_timeout_injection(self):
        # Simple SSH invocation
        mod, changed = inject_ssh_timeouts("ssh knot-desktop")
        self.assertTrue(changed)
        expected = "ssh -o ControlMaster=auto -o ControlPath=~/.cache/psl/ssh/cm_%C -o ControlPersist=10m -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 knot-desktop"
        self.assertEqual(mod, expected)

        # SSH with user, host, and remote command
        mod, changed = inject_ssh_timeouts("ssh user@knot-laptop uptime")
        self.assertTrue(changed)
        expected = "ssh -o ControlMaster=auto -o ControlPath=~/.cache/psl/ssh/cm_%C -o ControlPersist=10m -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 user@knot-laptop uptime"
        self.assertEqual(mod, expected)

        # Absolute binary path
        mod, changed = inject_ssh_timeouts("/usr/bin/ssh knot-deck")
        self.assertTrue(changed)
        expected = "/usr/bin/ssh -o ControlMaster=auto -o ControlPath=~/.cache/psl/ssh/cm_%C -o ControlPersist=10m -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 knot-deck"
        self.assertEqual(mod, expected)

        # Chained command
        mod, changed = inject_ssh_timeouts("echo ping && ssh knot-desktop")
        self.assertTrue(changed)
        expected = "echo ping && ssh -o ControlMaster=auto -o ControlPath=~/.cache/psl/ssh/cm_%C -o ControlPersist=10m -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 knot-desktop"
        self.assertEqual(mod, expected)

        # End-to-end via sanitize_command
        decision, mod_cmd, reason = sanitize_command("ssh knot-desktop")
        self.assertEqual(decision, "allow")
        self.assertIn("-o ControlMaster=auto", mod_cmd)
        self.assertIn("-o ConnectTimeout=10", mod_cmd)
        self.assertIn("-o BatchMode=yes", mod_cmd)
        self.assertIn("injected non-blocking SSH timeout and batch mode guards", reason)

        # Existing ConnectTimeout should not be touched
        existing_timeout = "ssh -o ConnectTimeout=10 knot-desktop"
        mod, changed = inject_ssh_timeouts(existing_timeout)
        self.assertFalse(changed)
        self.assertEqual(mod, existing_timeout)

        # Non-ssh commands containing 'ssh' substring or path
        non_ssh = [
            "cat ~/.ssh/config",
            "ssh-keygen -t ed25519",
            "ssh-copy-id knot-desktop",
            "git clone git@github.com:foo/bar.git",
        ]
        for cmd in non_ssh:
            mod, changed = inject_ssh_timeouts(cmd)
            self.assertFalse(changed, f"Should not inject for non-ssh command: {cmd}")
            self.assertEqual(mod, cmd)

    def test_idempotency(self):
        # PATH shims idempotency
        for cmd in ("pnpm build", "uv run pytest", "cargo test", "pytest tests/"):
            mod1, changed1 = inject_path_shims(cmd)
            self.assertTrue(changed1)
            mod2, changed2 = inject_path_shims(mod1)
            self.assertFalse(changed2)
            self.assertEqual(mod1, mod2)

        # SSH timeout idempotency
        mod1, changed1 = inject_ssh_timeouts("ssh knot-desktop")
        self.assertTrue(changed1)
        mod2, changed2 = inject_ssh_timeouts(mod1)
        self.assertFalse(changed2)
        self.assertEqual(mod1, mod2)

        # Full sanitize_command pipeline idempotency
        for cmd in ("pnpm test", "ssh knot-desktop"):
            decision1, mod1, reason1 = sanitize_command(cmd)
            self.assertEqual(decision1, "allow")
            self.assertIsNotNone(mod1)
            decision2, mod2, reason2 = sanitize_command(mod1)
            self.assertEqual(decision2, "allow")
            self.assertIsNone(mod2)
            self.assertIsNone(reason2)

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
            WHERE session_id = '270b7abc-9b59-4f50-9c49-de3ed7e04f06' AND step_index = 176
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

    def test_knot_exec_and_psl_remote_exec_ssh_pattern_matching(self):
        """Verifies SSH_PATTERN regex matches knot exec and psl remote exec."""
        # Simple commands
        m_knot = SSH_PATTERN.search("knot exec laptop 'uptime'")
        self.assertIsNotNone(m_knot)
        self.assertEqual(m_knot.group(2), "knot exec")

        m_psl = SSH_PATTERN.search("psl remote exec user@host 'uname -a'")
        self.assertIsNotNone(m_psl)
        self.assertEqual(m_psl.group(2), "psl remote exec")

        # Prefixed with sudo or nohup
        m_sudo_knot = SSH_PATTERN.search("sudo knot exec steamdeck 'whoami'")
        self.assertIsNotNone(m_sudo_knot)
        self.assertEqual(m_sudo_knot.group(2), "knot exec")

        m_nohup_psl = SSH_PATTERN.search("nohup psl remote exec worker 'sleep 10' &")
        self.assertIsNotNone(m_nohup_psl)
        self.assertEqual(m_nohup_psl.group(2), "psl remote exec")

        # Standard ssh still matches
        m_ssh = SSH_PATTERN.search("ssh user@target 'ls'")
        self.assertIsNotNone(m_ssh)
        self.assertEqual(m_ssh.group(2), "ssh")

    def test_knot_exec_and_psl_remote_exec_path_shims(self):
        """Verifies toolchain PATH shims apply cleanly to knot exec and psl remote exec."""
        mod_knot, changed_knot = inject_path_shims("knot exec laptop 'uptime'")
        self.assertTrue(changed_knot)
        self.assertIn('export PATH="', mod_knot)
        self.assertIn(':$PATH"; knot exec laptop \'uptime\'', mod_knot)

        mod_psl, changed_psl = inject_path_shims("psl remote exec worker 'uptime'")
        self.assertTrue(changed_psl)
        self.assertIn('export PATH="', mod_psl)
        self.assertIn(':$PATH"; psl remote exec worker \'uptime\'', mod_psl)

    def test_knot_exec_does_not_inject_openssh_options(self):
        """Knot exec and psl remote exec do not receive OpenSSH -o multiplex options directly."""
        mod_knot, changed_knot = inject_ssh_timeouts("knot exec laptop 'uptime'")
        self.assertFalse(changed_knot)
        self.assertEqual(mod_knot, "knot exec laptop 'uptime'")

        mod_psl, changed_psl = inject_ssh_timeouts("psl remote exec worker 'uptime'")
        self.assertFalse(changed_psl)
        self.assertEqual(mod_psl, "psl remote exec worker 'uptime'")

    def test_knot_exec_remote_sanitization(self):
        """Verifies knot exec and psl remote exec sanitize remote grep pattern probes and toolchains."""
        # Grep probe in knot exec
        mod1, changed1, reasons1 = sanitize_ssh_remote_payload("knot exec laptop 'grep -rn needle src/'")
        self.assertTrue(changed1)
        self.assertIn("|| [ $? -eq 1 ]", mod1)

        # Remote toolchain in psl remote exec
        mod2, changed2, reasons2 = sanitize_ssh_remote_payload("psl remote exec user@node 'pm2 restart all'")
        self.assertTrue(changed2)
        self.assertIn("bash -l -c 'pm2 restart all'", mod2)


if __name__ == "__main__":
    unittest.main()
