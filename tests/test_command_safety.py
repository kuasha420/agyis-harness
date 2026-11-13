#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unit and integration tests for harness/hooks/command_safety_hook.py
"""

import json
import os
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
            "rm -rf ~",
            "rm -rf ~/*",
            "rm -rf $HOME",
            "rm -rf ${HOME}",
            "git reset --hard",
            "git checkout -- .",
            "git clean -fd",
            "git clean -f",
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

    @patch("harness.hooks.command_safety_hook.find_hermetic_uv_python_bin")
    def test_hermetic_python_injection(self, mock_find):
        mock_find.return_value = Path("/home/mock/.local/share/uv/python/cpython-3.12.0-linux-x86_64-gnu/bin")
        decision, mod, reason = sanitize_command('python3 -c "data = {}; print(f\\\"{data.get(\'k\')}\\\")"')
        self.assertEqual(decision, "allow")
        self.assertIsNotNone(mod)
        self.assertIn('PATH="', mod)
        self.assertIn("cpython-3.1", mod)
        self.assertIn("python3 -c", mod)

    @patch("harness.hooks.command_safety_hook.find_hermetic_uv_python_bin")
    def test_hermetic_python_injection_script(self, mock_find):
        mock_find.return_value = Path("/home/mock/.local/share/uv/python/cpython-3.12.0-linux-x86_64-gnu/bin")
        decision, mod, reason = sanitize_command("python3 scripts/task.py")
        self.assertEqual(decision, "allow")
        self.assertIsNotNone(mod)
        self.assertIn('export PATH="', mod)
        self.assertIn("cpython-3.1", mod)
        self.assertIn("python3 scripts/task.py", mod)

    def test_systemd_pager_neutralization(self):
        for cmd in ("systemctl status", "journalctl -u docker", "udevadm monitor"):
            decision, mod, reason = sanitize_command(cmd)
            self.assertEqual(decision, "allow")
            self.assertIsNotNone(mod)
            self.assertTrue(mod.startswith("SYSTEMD_PAGER=cat "))
            self.assertIn("enforced non-interactive SYSTEMD_PAGER=cat", reason)

        # Commands already containing --no-pager or PAGER= should not be modified
        for cmd in ("systemctl status --no-pager", "PAGER=cat journalctl", "SYSTEMD_PAGER=cat udevadm"):
            decision, mod, reason = sanitize_command(cmd)
            self.assertEqual(decision, "allow")
            self.assertIsNone(mod)

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

    def test_decoupled_grep_tail_rewrite(self):
        # Grep commands must NOT have || [ $? -eq 1 ] appended automatically
        decision, mod, reason = sanitize_command("grep -rn 'needle' src/")
        self.assertEqual(decision, "allow")
        self.assertIsNone(mod)

        # Pipeline with git still receives PAGER=cat but no grep tail rewrite
        decision, mod, reason = sanitize_command("git diff | grep 'class '")
        self.assertEqual(decision, "allow")
        self.assertEqual(mod, "PAGER=cat git diff | grep 'class '")

    def test_fstring_and_double_quotes_preserved_without_corruption(self):
        """Verifies that bash commands containing double quotes inside expressions are not corrupted."""
        cmds = [
            'python3 -c "print(\'hello\')"',
            'python3 -c "import sys; print(f\\\"{sys.version}\\\")"',
            'python3 -c "data = {\'k\': \'v\'}; print(f\\\"{data.get(\'k\')}\\\")"',
            'python3 -c "msg = \\\"test\\\"; print(msg)"',
        ]
        for raw in cmds:
            decision, mod, reason = sanitize_command(raw)
            self.assertEqual(decision, "allow")
            checked_cmd = mod if mod is not None else raw
            self.assertIn(raw, checked_cmd)

    def test_get_user_path_shims(self):
        shims = get_user_path_shims()
        self.assertIsInstance(shims, list)
        for s in shims:
            self.assertTrue(Path(s).is_dir())

        # Test discovery with mocked directories
        with patch("pathlib.Path.is_dir") as mock_is_dir:
            # All 5 candidate dirs exist
            mock_is_dir.return_value = True
            mocked_shims = get_user_path_shims()
            self.assertEqual(len(mocked_shims), 5)
            self.assertTrue(any(".local/bin" in s for s in mocked_shims))
            self.assertTrue(any(".cargo/bin" in s for s in mocked_shims))
            self.assertTrue(any(".local/share/pnpm" in s for s in mocked_shims))
            self.assertTrue(any(".npm-global/bin" in s for s in mocked_shims))
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
        """Asserts that invoking `agyis` and `psl` subcommands triggers inject_path_shims (USER_TOOLCHAINS)."""
        commands = (
            "agyis test",
            "agyis doctor",
            "agyis harmonize",
            "agyis init",
            "agyis skills",
            "agyis agents",
            "psl test",
            "psl doctor",
            "psl harmonize",
            "psl init",
        )
        for cmd in commands:
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
            # Under PSL-INV-002 §4 and Issue #101 (RC10), this complex multi-line command is
            # transparently promoted to a temporary scratch file and allowed
            decision, mod_cmd, reason = sanitize_command(cmd)
            self.assertEqual(decision, "allow")
            self.assertIsNotNone(mod_cmd)
            self.assertIn(".agents/scratch/exec_", mod_cmd)
            self.assertIn("[AGYIS COGNITIVE HINT]", reason or "")

            # When promote_scratch is False, verify it is safely denied per PSL-INV-002 §4
            denied_dec, denied_mod, denied_reason = sanitize_command(cmd, promote_scratch=False)
            self.assertEqual(denied_dec, "deny")
            self.assertIn("PSL-INV-002 VIOLATION", denied_reason or "")

            # When bypassed via PSL_ALLOW_INLINE_SCRIPTS=1, verify hermetic Python injection occurs
            old_bypass = os.environ.get("PSL_ALLOW_INLINE_SCRIPTS")
            try:
                os.environ["PSL_ALLOW_INLINE_SCRIPTS"] = "1"
                decision, mod_cmd, reason = sanitize_command(cmd)
                self.assertEqual(decision, "allow")
                self.assertIsNotNone(mod_cmd)
                self.assertIn("cpython-3.12", mod_cmd)
                self.assertIn("PATH=", mod_cmd)

                # Under PSL-SPEC-2026-DRA-001 Section 6.2.1, naive regex substitution was eliminated
                # from command_safety_hook to preserve bash quoting. Verify hermetic Python injection
                # occurred without mutating raw script syntax.
                self.assertIn("python3 -c", mod_cmd)
            finally:
                if old_bypass is not None:
                    os.environ["PSL_ALLOW_INLINE_SCRIPTS"] = old_bypass
                else:
                    os.environ.pop("PSL_ALLOW_INLINE_SCRIPTS", None)

    def test_knot_exec_and_psl_remote_exec_ssh_pattern_matching(self):
        """Verifies SSH_PATTERN regex matches knot exec, agyis remote exec, and psl remote exec."""
        # Simple commands
        m_knot = SSH_PATTERN.search("knot exec laptop 'uptime'")
        self.assertIsNotNone(m_knot)
        self.assertEqual(m_knot.group(2), "knot exec")

        m_agyis = SSH_PATTERN.search("agyis remote exec user@host 'uname -a'")
        self.assertIsNotNone(m_agyis)
        self.assertEqual(m_agyis.group(2), "agyis remote exec")

        m_psl = SSH_PATTERN.search("psl remote exec user@host 'uname -a'")
        self.assertIsNotNone(m_psl)
        self.assertEqual(m_psl.group(2), "psl remote exec")

        # Prefixed with sudo or nohup
        m_sudo_knot = SSH_PATTERN.search("sudo knot exec steamdeck 'whoami'")
        self.assertIsNotNone(m_sudo_knot)
        self.assertEqual(m_sudo_knot.group(2), "knot exec")

        m_sudo_agyis = SSH_PATTERN.search("sudo agyis remote exec worker 'whoami'")
        self.assertIsNotNone(m_sudo_agyis)
        self.assertEqual(m_sudo_agyis.group(2), "agyis remote exec")

        m_nohup_psl = SSH_PATTERN.search("nohup psl remote exec worker 'sleep 10' &")
        self.assertIsNotNone(m_nohup_psl)
        self.assertEqual(m_nohup_psl.group(2), "psl remote exec")

        m_nohup_agyis = SSH_PATTERN.search("nohup agyis remote exec worker 'sleep 10' &")
        self.assertIsNotNone(m_nohup_agyis)
        self.assertEqual(m_nohup_agyis.group(2), "agyis remote exec")

        # Standard ssh still matches
        m_ssh = SSH_PATTERN.search("ssh user@target 'ls'")
        self.assertIsNotNone(m_ssh)
        self.assertEqual(m_ssh.group(2), "ssh")

    def test_knot_exec_and_psl_remote_exec_path_shims(self):
        """Verifies toolchain PATH shims apply cleanly to knot exec, agyis remote exec, and psl remote exec."""
        mod_knot, changed_knot = inject_path_shims("knot exec laptop 'uptime'")
        self.assertTrue(changed_knot)
        self.assertIn('export PATH="', mod_knot)
        self.assertIn(':$PATH"; knot exec laptop \'uptime\'', mod_knot)

        mod_agyis, changed_agyis = inject_path_shims("agyis remote exec worker 'uptime'")
        self.assertTrue(changed_agyis)
        self.assertIn('export PATH="', mod_agyis)
        self.assertIn(':$PATH"; agyis remote exec worker \'uptime\'', mod_agyis)

        mod_psl, changed_psl = inject_path_shims("psl remote exec worker 'uptime'")
        self.assertTrue(changed_psl)
        self.assertIn('export PATH="', mod_psl)
        self.assertIn(':$PATH"; psl remote exec worker \'uptime\'', mod_psl)

    def test_knot_exec_does_not_inject_openssh_options(self):
        """Knot exec, agyis remote exec, and psl remote exec do not receive OpenSSH -o multiplex options directly."""
        mod_knot, changed_knot = inject_ssh_timeouts("knot exec laptop 'uptime'")
        self.assertFalse(changed_knot)
        self.assertEqual(mod_knot, "knot exec laptop 'uptime'")

        mod_agyis, changed_agyis = inject_ssh_timeouts("agyis remote exec worker 'uptime'")
        self.assertFalse(changed_agyis)
        self.assertEqual(mod_agyis, "agyis remote exec worker 'uptime'")

        mod_psl, changed_psl = inject_ssh_timeouts("psl remote exec worker 'uptime'")
        self.assertFalse(changed_psl)
        self.assertEqual(mod_psl, "psl remote exec worker 'uptime'")

    def test_knot_exec_remote_sanitization(self):
        """Verifies knot exec, agyis remote exec, and psl remote exec sanitize remote grep pattern probes and toolchains."""
        # Grep probe in knot exec
        mod1, changed1, reasons1 = sanitize_ssh_remote_payload("knot exec laptop 'grep -rn needle src/'")
        self.assertTrue(changed1)
        self.assertIn("|| [ $? -eq 1 ]", mod1)

        mod2, changed2, reasons2 = sanitize_ssh_remote_payload("psl remote exec user@node 'pm2 restart all'")
        self.assertTrue(changed2)
        self.assertIn("bash -l -c 'pm2 restart all'", mod2)

        mod3, changed3, reasons3 = sanitize_ssh_remote_payload("agyis remote exec user@node 'pm2 restart all'")
        self.assertTrue(changed3)
        self.assertIn("bash -l -c 'pm2 restart all'", mod3)

        mod4, changed4, reasons4 = sanitize_ssh_remote_payload("agyis remote exec laptop 'grep -rn needle src/'")
        self.assertTrue(changed4)
        self.assertIn("|| [ $? -eq 1 ]", mod4)

    def test_preflight_tool_availability_guard(self):
        """
        Verifies command safety hook behavior on missing CLI binaries (Exit Code 127)
        and validates package install suggestions per ADR-013 §1.
        """
        import io
        from harness.hooks.command_safety_hook import (
            check_preflight_tool_availability,
            extract_command_binary,
            main as safety_main,
        )

        # 1. Test binary extraction
        self.assertEqual(extract_command_binary("pnpm test --filter foo"), "pnpm")
        self.assertEqual(extract_command_binary("PAGER=cat git log"), "git")
        self.assertEqual(extract_command_binary("sudo apt update"), "apt")
        self.assertEqual(extract_command_binary("VAR=1 OTHER=2 ollama serve"), "ollama")
        self.assertIsNone(extract_command_binary(""))

        # 2. Builtin / shell commands pass without error
        builtin_res = check_preflight_tool_availability("echo 'hello world'")
        self.assertTrue(builtin_res["available"])
        self.assertEqual(builtin_res["binary"], "echo")

        # 3. Simulate missing binaries (Exit 127 prevention)
        with patch("shutil.which", return_value=None), patch("harness.hooks.command_safety_hook.get_user_path_shims", return_value=[]):
            # pnpm missing -> returns suggestion
            pnpm_res = check_preflight_tool_availability("pnpm install")
            self.assertFalse(pnpm_res["available"])
            self.assertEqual(pnpm_res["exit_code_risk"], 127)
            self.assertIn("pnpm", pnpm_res["suggestion"])
            self.assertIn("PSL Preflight Guard", pnpm_res["warning"])

            # ollama missing -> returns ollama install suggestion
            ollama_res = check_preflight_tool_availability("ollama run llama3")
            self.assertFalse(ollama_res["available"])
            self.assertEqual(ollama_res["exit_code_risk"], 127)
            self.assertIn("ollama", ollama_res["suggestion"].lower())

            # arbitrary unknown tool -> returns generic suggestion
            unknown_res = check_preflight_tool_availability("unknown_custom_cli_xyz --flag")
            self.assertFalse(unknown_res["available"])
            self.assertEqual(unknown_res["exit_code_risk"], 127)
            self.assertIn("unknown_custom_cli_xyz", unknown_res["suggestion"])

            # 4. Direct sanitize_command with check_preflight=True
            decision, mod, reason = sanitize_command("pawthy run", check_preflight=True)
            self.assertEqual(decision, "deny")
            self.assertIn("Missing CLI binary 'pawthy'", reason)

            # 5. End-to-end hook main() execution with check_preflight payload
            payload = {
                "check_preflight": True,
                "toolCall": {"name": "run_command", "args": {"CommandLine": "cargo test"}},
            }
            with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                safety_main()
                res = json.loads(mock_out.getvalue().strip())
                self.assertFalse(res["available"])
                self.assertEqual(res["binary"], "cargo")
                self.assertEqual(res["exit_code_risk"], 127)


class TestCommandSafetyDualToolchains(unittest.TestCase):
    """Hermetic unit tests validating dual toolchain recognition for agyis and psl."""

    def test_user_toolchains_contains_both_agyis_and_psl(self):
        """Verifies USER_TOOLCHAINS in command_safety_hook includes both agyis and psl."""
        from harness.hooks.command_safety_hook import USER_TOOLCHAINS
        self.assertIn("agyis", USER_TOOLCHAINS)
        self.assertIn("psl", USER_TOOLCHAINS)

    def test_preflight_binary_extraction_dual(self):
        """Verifies extract_command_binary recognizes agyis and psl with various wrappers."""
        from harness.hooks.command_safety_hook import extract_command_binary
        self.assertEqual(extract_command_binary("agyis doctor"), "agyis")
        self.assertEqual(extract_command_binary("psl doctor"), "psl")
        self.assertEqual(extract_command_binary("sudo agyis test"), "agyis")
        self.assertEqual(extract_command_binary("nohup psl test &"), "psl")
        self.assertEqual(extract_command_binary("time agyis harmonize"), "agyis")

    def test_remote_payload_sanitization_dual(self):
        """Verifies sanitize_ssh_remote_payload treats agyis remote exec and psl remote exec identically."""
        # Toolchain promotion
        c1, ch1, _ = sanitize_ssh_remote_payload("agyis remote exec host 'pm2 restart all'")
        self.assertTrue(ch1)
        self.assertIn("bash -l -c 'pm2 restart all'", c1)

        c2, ch2, _ = sanitize_ssh_remote_payload("psl remote exec host 'pm2 restart all'")
        self.assertTrue(ch2)
        self.assertIn("bash -l -c 'pm2 restart all'", c2)

        # Pattern probe sanitization
        p1, pch1, _ = sanitize_ssh_remote_payload("agyis remote exec host 'grep needle file.txt'")
        self.assertTrue(pch1)
        self.assertIn("|| [ $? -eq 1 ]", p1)

        p2, pch2, _ = sanitize_ssh_remote_payload("psl remote exec host 'grep needle file.txt'")
        self.assertTrue(pch2)
        self.assertIn("|| [ $? -eq 1 ]", p2)


class TestRC10Cluster1ToolResilience(unittest.TestCase):
    """Hermetic unit tests for RC10 Cluster 1: Issues #101, #102, #104."""

    def test_argument_sanitization_prepends_cwd_and_deletes_key(self):
        """Foreign Cwd and cwd properties are safely converted to cd navigation and stripped (#104)."""
        from harness.hooks.command_safety_hook import sanitize_run_command_args

        # 1. Capitalized Cwd
        args1 = {"CommandLine": "pnpm test", "Cwd": "/repo/project"}
        cleaned1, mod1, reasons1 = sanitize_run_command_args(args1)
        self.assertTrue(mod1)
        self.assertEqual(cleaned1["CommandLine"], 'cd "/repo/project" && pnpm test')
        self.assertNotIn("Cwd", cleaned1)
        self.assertNotIn("cwd", cleaned1)

        # 2. Lowercase cwd
        args2 = {"CommandLine": "cargo check", "cwd": "/home/user/rust"}
        cleaned2, mod2, reasons2 = sanitize_run_command_args(args2)
        self.assertTrue(mod2)
        self.assertEqual(cleaned2["CommandLine"], 'cd "/home/user/rust" && cargo check')
        self.assertNotIn("cwd", cleaned2)

        # 3. Cwd with empty CommandLine
        args3 = {"Cwd": "/tmp"}
        cleaned3, mod3, reasons3 = sanitize_run_command_args(args3)
        self.assertTrue(mod3)
        self.assertEqual(cleaned3["CommandLine"], 'cd "/tmp"')
        self.assertNotIn("Cwd", cleaned3)

    def test_argument_sanitization_strips_foreign_properties(self):
        """Unrecognized foreign properties (toolAction, timeout) are stripped while schema keys are preserved (#104)."""
        from harness.hooks.command_safety_hook import RUN_COMMAND_ALLOWED_KEYS, sanitize_run_command_args

        args = {
            "CommandLine": "git status",
            "WaitMsBeforeAsync": 5000,
            "IsDaemon": False,
            "toolSummary": "Git status check",
            "toolAction": "execute",
            "timeout": 30,
            "description": "Run git status",
        }
        cleaned, mod, reasons = sanitize_run_command_args(args)
        self.assertTrue(mod)
        self.assertEqual(cleaned["CommandLine"], "git status")
        self.assertEqual(cleaned["WaitMsBeforeAsync"], 5000)
        self.assertEqual(cleaned["IsDaemon"], False)
        self.assertEqual(cleaned["toolSummary"], "Git status check")

        # Foreign keys stripped
        self.assertNotIn("toolAction", cleaned)
        self.assertNotIn("timeout", cleaned)
        self.assertNotIn("description", cleaned)

        # All output keys must conform to native schema
        for k in cleaned.keys():
            self.assertIn(k, RUN_COMMAND_ALLOWED_KEYS)

    def test_argument_sanitization_hook_main_json_overwrite(self):
        """End-to-end stdin/stdout hook main() sanitizes foreign properties into overwrite (#104)."""
        import io
        from harness.hooks.command_safety_hook import main as safety_main

        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {
                    "CommandLine": "pytest tests/",
                    "Cwd": "/workspace/service",
                    "toolAction": "test_runner",
                    "WaitMsBeforeAsync": 2000,
                },
            }
        }
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            safety_main()
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")
            self.assertIn("overwrite", res)
            ow = res["overwrite"]
            self.assertIn('cd "/workspace/service" && pytest tests/', ow["CommandLine"])
            self.assertEqual(ow["WaitMsBeforeAsync"], 2000)
            self.assertNotIn("Cwd", ow)
            self.assertNotIn("toolAction", ow)
            self.assertIn("prepended directory navigation", res.get("reason", ""))

    def test_scratch_promotion_python(self):
        """Multi-line Python inline script is promoted to a verified absolute .agents/scratch/exec_<hash>.py (#101)."""
        import tempfile
        from harness.hooks.command_safety_hook import promote_inline_script_to_scratch

        with tempfile.TemporaryDirectory() as td:
            ws = Path(td).resolve()
            multiline_cmd = "python3 -c \"import os\nprint(os.environ.get('USER'))\""
            decision, mod_cmd, reason = promote_inline_script_to_scratch(multiline_cmd, workspace_dir=ws)

            self.assertEqual(decision, "allow")
            self.assertIsNotNone(mod_cmd)
            parts = mod_cmd.split()
            self.assertEqual(parts[0], "python3")
            scratch_file = Path(parts[1])
            self.assertTrue(scratch_file.is_absolute())
            self.assertTrue(scratch_file.is_relative_to(ws / ".agents" / "scratch"))
            self.assertTrue(mod_cmd.endswith(".py"))
            self.assertIn("[AGYIS COGNITIVE HINT]", reason)
            self.assertTrue(scratch_file.is_file())
            content = scratch_file.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("# Transparently promoted by PSL command_safety_hook (PSL-INV-002)\n"))
            self.assertIn("import os\nprint(os.environ.get('USER'))", content)

    def test_scratch_promotion_bash_and_sh_executable(self):
        """Multi-line Bash and Sh scripts are promoted to verified absolute paths with chmod +x (#101)."""
        import tempfile
        from harness.hooks.command_safety_hook import promote_inline_script_to_scratch

        with tempfile.TemporaryDirectory() as td:
            ws = Path(td).resolve()
            bash_cmd = "bash -c \"echo line1\necho line2\""
            dec_b, mod_b, _ = promote_inline_script_to_scratch(bash_cmd, workspace_dir=ws)
            self.assertEqual(dec_b, "allow")
            scratch_b = Path(mod_b.split()[1])
            self.assertEqual(mod_b.split()[0], "bash")
            self.assertTrue(scratch_b.is_absolute() and scratch_b.is_relative_to(ws / ".agents" / "scratch"))
            self.assertTrue(mod_b.endswith(".sh"))
            self.assertTrue(scratch_b.is_file() and bool(scratch_b.stat().st_mode & 0o111))
            self.assertIn("# Transparently promoted by PSL command_safety_hook", scratch_b.read_text())

            sh_cmd = "sh -c \"echo sh1\necho sh2\""
            dec_s, mod_s, _ = promote_inline_script_to_scratch(sh_cmd, workspace_dir=ws)
            self.assertEqual(dec_s, "allow")
            scratch_s = Path(mod_s.split()[1])
            self.assertEqual(mod_s.split()[0], "sh")
            self.assertTrue(scratch_s.is_absolute() and scratch_s.is_relative_to(ws / ".agents" / "scratch"))
            self.assertTrue(mod_s.endswith(".sh") and bool(scratch_s.stat().st_mode & 0o111))

    def test_scratch_promotion_node_valid_js_comment(self):
        """Multi-line Node scripts are promoted to absolute .js files with valid // comment headers (#101)."""
        import tempfile
        from harness.hooks.command_safety_hook import promote_inline_script_to_scratch

        with tempfile.TemporaryDirectory() as td:
            ws = Path(td).resolve()
            node_cmd = "node -e \"const os = require('os')\nconsole.log(os.platform())\""
            dec, mod, _ = promote_inline_script_to_scratch(node_cmd, workspace_dir=ws)
            self.assertEqual(dec, "allow")
            scratch_js = Path(mod.split()[1])
            self.assertEqual(mod.split()[0], "node")
            self.assertTrue(scratch_js.is_absolute() and scratch_js.is_relative_to(ws / ".agents" / "scratch"))
            self.assertTrue(mod.endswith(".js"))
            content = scratch_js.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("// Transparently promoted by PSL command_safety_hook (PSL-INV-002)\n"))

    def test_scratch_promotion_fallback_on_write_failure(self):
        """When scratch file creation fails, promotion gracefully falls back to deny (#101)."""
        from harness.hooks.command_safety_hook import promote_inline_script_to_scratch

        cmd = "python3 -c \"import os\nprint(1)\""
        with patch("harness.hooks.command_safety_hook.resolve_scratch_target_path", side_effect=OSError("Read-only filesystem")):
            decision, mod, reason = promote_inline_script_to_scratch(cmd)
            self.assertEqual(decision, "deny")
            self.assertIsNone(mod)
            self.assertIn("PSL-INV-002 VIOLATION", reason)

    def test_combined_cwd_and_scratch_promotion_end_to_end(self):
        """End-to-end foreign Cwd sanitization + workspacePaths absolute scratch promotion (#101 + #104)."""
        import io
        import tempfile
        from harness.hooks.command_safety_hook import main as safety_main

        with tempfile.TemporaryDirectory() as td:
            ws = Path(td).resolve()
            payload = {
                "workspacePaths": [str(ws)],
                "toolCall": {
                    "name": "run_command",
                    "args": {
                        "CommandLine": "python3 -c \"import sys\nprint('hello from subfolder')\"",
                        "Cwd": "/opt/custom",
                        "toolAction": "eval",
                    },
                },
            }
            with patch("sys.stdin", io.StringIO(json.dumps(payload))), \
                 patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                safety_main()
                res = json.loads(mock_out.getvalue().strip())
                self.assertEqual(res["decision"], "allow")
                ow = res["overwrite"]
                cmd = ow["CommandLine"]
                expected_prefix = f'cd "/opt/custom" && python3 {ws}/.agents/scratch/exec_'
                self.assertIn(expected_prefix, cmd, f"Unexpected cmd: {cmd}")
                self.assertTrue(cmd.endswith(".py"))
                self.assertNotIn("Cwd", ow)
                self.assertNotIn("toolAction", ow)
                self.assertIn("prepended directory navigation", res.get("reason", ""))
                self.assertIn("[AGYIS COGNITIVE HINT]", res.get("reason", ""))

    def test_scratch_promotion_with_flag_in_script_body(self):
        """Scripts containing flag characters (-c / -e) in the body do not corrupt CommandLine rewriting (Defect 1)."""
        import tempfile
        from harness.hooks.command_safety_hook import promote_inline_script_to_scratch

        with tempfile.TemporaryDirectory() as td:
            ws = Path(td).resolve()
            py_cmd = "python3 -c \"import subprocess\nsubprocess.run(['bash', '-c', 'echo 1'])\""
            dec_py, mod_py, _ = promote_inline_script_to_scratch(py_cmd, workspace_dir=ws)
            self.assertEqual(dec_py, "allow")
            self.assertEqual(len(mod_py.split()), 2)
            py_file = Path(mod_py.split()[1])
            self.assertTrue(py_file.is_absolute() and py_file.is_relative_to(ws / ".agents" / "scratch"))
            self.assertTrue(mod_py.endswith(".py"))
            self.assertIn("subprocess.run(['bash', '-c', 'echo 1'])", py_file.read_text())

            node_cmd = "node -e \"const cp = require('child_process')\ncp.execSync('echo -e hello')\""
            dec_node, mod_node, _ = promote_inline_script_to_scratch(node_cmd, workspace_dir=ws)
            self.assertEqual(dec_node, "allow")
            self.assertEqual(len(mod_node.split()), 2)
            node_file = Path(mod_node.split()[1])
            self.assertTrue(node_file.is_absolute() and node_file.is_relative_to(ws / ".agents" / "scratch"))
            self.assertTrue(mod_node.endswith(".js"))
            self.assertIn("cp.execSync('echo -e hello')", node_file.read_text())

    def test_scratch_promotion_multiple_interpreters_order_preservation(self):
        """Compound commands with multiple interpreters rewrite cleanly right-to-left without offset drift (Defect 2)."""
        import tempfile
        from harness.hooks.command_safety_hook import promote_inline_script_to_scratch

        with tempfile.TemporaryDirectory() as td:
            ws = Path(td).resolve()
            compound = (
                "bash -c \"echo step1\necho step1_done\" && "
                "python3 -c \"import sys\nprint('step2')\""
            )
            dec, mod, _ = promote_inline_script_to_scratch(compound, workspace_dir=ws)
            self.assertEqual(dec, "allow")
            parts = mod.split(" && ")
            self.assertEqual(len(parts), 2)

            bash_file = Path(parts[0].split()[1])
            py_file = Path(parts[1].split()[1])
            self.assertEqual(parts[0].split()[0], "bash")
            self.assertEqual(parts[1].split()[0], "python3")
            self.assertTrue(bash_file.is_absolute() and bash_file.is_relative_to(ws / ".agents" / "scratch") and parts[0].endswith(".sh"))
            self.assertTrue(py_file.is_absolute() and py_file.is_relative_to(ws / ".agents" / "scratch") and parts[1].endswith(".py"))
            self.assertIn("echo step1", bash_file.read_text())
            self.assertIn("import sys", py_file.read_text())


if __name__ == "__main__":
    unittest.main()
