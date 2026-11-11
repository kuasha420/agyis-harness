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
import tempfile
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



class TestZeroKillPauseSafetyGuard(unittest.TestCase):
    """Hermetic unit tests for Zero-Kill Swarm Parking PreToolUse safety guard."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.artifacts_dir = self.workspace / ".agents" / "artifacts"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_manage_subagents_kill_blocked_when_pause_gate_active(self):
        pause_file = self.artifacts_dir / "pause_gate.json"
        pause_file.write_text(json.dumps({"status": "paused", "reason": "token_fence"}))

        from harness.hooks.command_safety_hook import check_pause_safety
        decision, reason = check_pause_safety("manage_subagents", {"Action": "kill", "Target": "worker-1"}, self.workspace)
        self.assertEqual(decision, "deny")
        self.assertIn("Zero-Kill Swarm Parking Invariant", reason)

    def test_manage_subagents_kill_all_and_cancel_blocked(self):
        pause_file = self.artifacts_dir / "pause_gate.json"
        pause_file.write_text(json.dumps({"status": "pausing"}))

        from harness.hooks.command_safety_hook import check_pause_safety
        for action in ["kill_all", "cancel"]:
            decision, reason = check_pause_safety("manage_subagents", {"Action": action}, self.workspace)
            self.assertEqual(decision, "deny")
            self.assertIn("Zero-Kill Swarm Parking Invariant", reason)

    def test_manage_task_kill_and_cancel_blocked(self):
        pause_file = self.artifacts_dir / "pause_gate.json"
        pause_file.write_text(json.dumps({"status": "paused"}))

        from harness.hooks.command_safety_hook import check_pause_safety
        for action in ["kill", "cancel"]:
            decision, reason = check_pause_safety("manage_task", {"Action": action, "TaskId": "task-1"}, self.workspace)
            self.assertEqual(decision, "deny")
            self.assertIn("Zero-Kill Swarm Parking Invariant", reason)

    def test_manage_task_status_and_subagents_list_allowed(self):
        pause_file = self.artifacts_dir / "pause_gate.json"
        pause_file.write_text(json.dumps({"status": "paused"}))

        from harness.hooks.command_safety_hook import check_pause_safety
        decision, reason = check_pause_safety("manage_task", {"Action": "status", "TaskId": "task-1"}, self.workspace)
        self.assertEqual(decision, "allow")
        self.assertIsNone(reason)

        decision2, reason2 = check_pause_safety("manage_subagents", {"Action": "list"}, self.workspace)
        self.assertEqual(decision2, "allow")
        self.assertIsNone(reason2)

    def test_shell_kill_9_and_pkill_9_blocked_when_pause_gate_active(self):
        pause_file = self.artifacts_dir / "pause_gate.json"
        pause_file.write_text(json.dumps({"status": "paused"}))

        from harness.hooks.command_safety_hook import check_pause_safety
        for cmd in ["kill -9 1234", "pkill -9 python", "killall -SIGKILL node", "kill -KILL 5678"]:
            decision, reason = check_pause_safety("run_command", {"CommandLine": cmd}, self.workspace)
            self.assertEqual(decision, "deny")
            self.assertIn("Zero-Kill Swarm Parking Invariant", reason)

    def test_fail_open_on_malformed_json_or_io_error(self):
        pause_file = self.artifacts_dir / "pause_gate.json"
        pause_file.write_text("{not-valid-json!!")

        from harness.hooks.command_safety_hook import check_pause_safety
        decision, reason = check_pause_safety("manage_subagents", {"Action": "kill"}, self.workspace)
        self.assertEqual(decision, "allow")
        self.assertIsNone(reason)

    def test_execution_allowed_when_no_pause_gate(self):
        from harness.hooks.command_safety_hook import check_pause_safety
        decision, reason = check_pause_safety("manage_subagents", {"Action": "kill"}, self.workspace)
        self.assertEqual(decision, "allow")
        self.assertIsNone(reason)

    def test_hook_main_integration_with_pause_gate(self):
        pause_file = self.artifacts_dir / "pause_gate.json"
        pause_file.write_text(json.dumps({"status": "paused"}))

        from harness.hooks.command_safety_hook import main as safety_main
        payload = {
            "toolCall": {
                "name": "manage_subagents",
                "args": {"Action": "kill", "Target": "worker-1"},
            }
        }
        with patch("harness.hooks.command_safety_hook.Path.cwd", return_value=self.workspace), \
             patch("sys.stdin", io.StringIO(json.dumps(payload))), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            safety_main()
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "deny")
            self.assertIn("Zero-Kill Swarm Parking Invariant", res["reason"])


class TestInlineScriptHygieneHook(unittest.TestCase):
    """Hermetic unit tests for PSL-INV-002 §4 inline script hygiene hook (<0.05s SLA)."""

    def test_short_safe_inline_script_allowed(self):
        """Short safe one-liners without newlines or excessive length are allowed."""
        from harness.hooks.command_safety_hook import check_inline_script_hygiene
        decision, reason = check_inline_script_hygiene("python3 -c \"print('ok')\"")
        self.assertEqual(decision, "allow")
        self.assertIsNone(reason)

        decision2, reason2 = check_inline_script_hygiene("node -e \"console.log('ok')\"")
        self.assertEqual(decision2, "allow")
        self.assertIsNone(reason2)

        decision3, reason3 = check_inline_script_hygiene("bash -c \"echo ok\"")
        self.assertEqual(decision3, "allow")
        self.assertIsNone(reason3)

    def test_multiline_script_literal_or_escaped_newline_denied(self):
        """Multi-line inline script with literal newline or \\n escape is denied."""
        from harness.hooks.command_safety_hook import check_inline_script_hygiene
        # Literal newline
        literal_cmd = "python3 -c \"import os\nprint(os.getcwd())\""
        decision, reason = check_inline_script_hygiene(literal_cmd)
        self.assertEqual(decision, "deny")
        self.assertIn("PSL-INV-002 VIOLATION", reason)
        self.assertIn("scratch/probe.py", reason)

        # Escaped newline (\n in command string)
        escaped_cmd = r'python3 -c "import os\nprint(os.getcwd())"'
        decision2, reason2 = check_inline_script_hygiene(escaped_cmd)
        self.assertEqual(decision2, "deny")
        self.assertIn("PSL-INV-002 VIOLATION", reason2)

    def test_single_line_up_to_250_chars_allowed_and_over_250_denied(self):
        """Single-line inline script <= 250 chars is allowed; > 250 chars is denied (Issue #102)."""
        from harness.hooks.command_safety_hook import check_inline_script_hygiene
        # 1. 200 chars newline-free -> allowed
        body_200 = "x = '" + ("a" * 180) + "'; print(x)"
        cmd_200 = f'python3 -c "{body_200}"'
        decision, reason = check_inline_script_hygiene(cmd_200)
        self.assertEqual(decision, "allow")
        self.assertIsNone(reason)

        # 2. Exactly 250 chars stripped -> allowed
        prefix = "x = '"
        suffix = "'; print(x)"
        body_250 = prefix + ("a" * (250 - len(prefix) - len(suffix))) + suffix
        self.assertEqual(len(body_250.strip()), 250)
        cmd_250 = f'python3 -c "{body_250}"'
        decision, reason = check_inline_script_hygiene(cmd_250)
        self.assertEqual(decision, "allow")
        self.assertIsNone(reason)

        # 3. 251 chars -> denied by hygiene validator
        body_251 = prefix + ("a" * (251 - len(prefix) - len(suffix))) + suffix
        self.assertEqual(len(body_251.strip()), 251)
        cmd_251 = f'python3 -c "{body_251}"'
        decision, reason = check_inline_script_hygiene(cmd_251)
        self.assertEqual(decision, "deny")
        self.assertIn("PSL-INV-002 VIOLATION", reason)
        self.assertIn(">250 chars or newlines", reason)

    def test_node_and_bash_multiline_and_long_scripts_denied(self):
        """node -e, bash -c, and sh -c multi-line scripts are denied by hygiene validator."""
        from harness.hooks.command_safety_hook import check_inline_script_hygiene
        node_cmd = "node -e \"const fs = require('fs')\nconsole.log(fs.readdirSync('.'))\""
        decision_node, reason_node = check_inline_script_hygiene(node_cmd)
        self.assertEqual(decision_node, "deny")
        self.assertIn("PSL-INV-002 VIOLATION", reason_node)

        bash_cmd = "bash -c \"echo line1\necho line2\""
        decision_bash, reason_bash = check_inline_script_hygiene(bash_cmd)
        self.assertEqual(decision_bash, "deny")
        self.assertIn("PSL-INV-002 VIOLATION", reason_bash)

        sh_cmd = "sh -c \"echo line1\necho line2\""
        decision_sh, reason_sh = check_inline_script_hygiene(sh_cmd)
        self.assertEqual(decision_sh, "deny")
        self.assertIn("PSL-INV-002 VIOLATION", reason_sh)

    def test_inline_comment_bypass(self):
        """Directive comments (# agyis: allow-inline-script / # allow-inline) bypass hygiene deny."""
        from harness.hooks.command_safety_hook import check_inline_script_hygiene
        cmd1 = "python3 -c \"import os\nprint(os.getcwd())\" # agyis: allow-inline-script"
        decision1, reason1 = check_inline_script_hygiene(cmd1)
        self.assertEqual(decision1, "allow")
        self.assertIsNone(reason1)

        cmd2 = "python3 -c \"import os\nprint(os.getcwd())\" # allow-inline"
        decision2, reason2 = check_inline_script_hygiene(cmd2)
        self.assertEqual(decision2, "allow")
        self.assertIsNone(reason2)

    def test_env_var_bypass(self):
        """Setting PSL_ALLOW_INLINE_SCRIPTS=1 environment variable bypasses hygiene deny."""
        from harness.hooks.command_safety_hook import check_inline_script_hygiene
        cmd = "python3 -c \"import os\nprint(os.getcwd())\""
        with patch.dict("os.environ", {"PSL_ALLOW_INLINE_SCRIPTS": "1"}):
            decision, reason = check_inline_script_hygiene(cmd)
            self.assertEqual(decision, "allow")
            self.assertIsNone(reason)

    def test_sanitize_command_integration(self):
        """sanitize_command promotes multi-line scripts to verified absolute scratch paths (#101)."""
        from harness.hooks.command_safety_hook import sanitize_command
        cmd = "python3 -c \"import os\nprint(os.getcwd())\""
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td).resolve()
            decision, mod_cmd, reason = sanitize_command(cmd, workspace_dir=ws)
            self.assertEqual(decision, "allow")
            self.assertIsNotNone(mod_cmd)
            self.assertIn(f"{ws}/.agents/scratch/exec_", mod_cmd)
            self.assertIn("[AGYIS COGNITIVE HINT]", reason)

        dec_fallback, mod_fallback, reason_fallback = sanitize_command(cmd, promote_scratch=False)
        self.assertEqual(dec_fallback, "deny")
        self.assertIsNone(mod_fallback)
        self.assertIn("PSL-INV-002 VIOLATION", reason_fallback)

    def test_workspace_paths_preference_and_plugin_cwd_brain_fallback(self):
        """workspacePaths picks <ws>/scratch/ if present, <ws>/.agents/scratch/ otherwise, or brain scratch when cwd is a plugin dir."""
        from harness.hooks.command_safety_hook import resolve_scratch_target_path

        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            ws1 = root / "ws_scratch"
            (ws1 / "scratch").mkdir(parents=True, exist_ok=True)
            t1, ref1 = resolve_scratch_target_path(".py", "abc12345", workspace_dir=ws1)
            self.assertTrue(t1.is_absolute() and t1.is_relative_to(ws1 / "scratch"))
            self.assertEqual(ref1, str(t1))

            ws2 = root / "ws_agents"
            ws2.mkdir(parents=True, exist_ok=True)
            t2, _ = resolve_scratch_target_path(".py", "def67890", workspace_dir=ws2)
            self.assertTrue(t2.is_absolute() and t2.is_relative_to(ws2 / ".agents" / "scratch"))

            brain = root / "brain"
            plugin_cwd = root / ".gemini" / "config" / "plugins" / "agyis-harness"
            plugin_cwd.mkdir(parents=True, exist_ok=True)
            with patch("harness.hooks.command_safety_hook.get_active_brain_dir", return_value=brain), \
                 patch("harness.hooks.command_safety_hook.Path.cwd", return_value=plugin_cwd), \
                 patch.dict("os.environ", {"AGYIS_CONVERSATION_ID": "conv-123"}):
                t3, _ = resolve_scratch_target_path(".py", "11223344")
                self.assertTrue(t3.is_relative_to(brain / "conv-123" / "scratch"))

    def test_export_path_syntax_valid_before_for_loop(self):
        """Hermetic python / shim PATH injection emits `export PATH="..."; ` valid before shell `for` loops."""
        import subprocess
        from harness.hooks.command_safety_hook import sanitize_command

        with patch("harness.hooks.command_safety_hook.find_hermetic_uv_python_bin", return_value=Path("/opt/uv python/bin")), \
             patch("harness.hooks.command_safety_hook.get_user_path_shims", return_value=["/home/user/.local/bin"]):
            for cmd in (
                'for f in a b; do python3 -c "print(\'hi\')"; done',
                'for f in a b; do uv run pytest && python3 -c "print(1)"; done',
            ):
                dec, mod_cmd, _ = sanitize_command(cmd)
                self.assertEqual(dec, "allow")
                self.assertIsNotNone(mod_cmd)
                self.assertTrue(mod_cmd.startswith('export PATH="'))
                res = subprocess.run(["bash", "-n", "-c", mod_cmd], capture_output=True, text=True)
                self.assertEqual(res.returncode, 0, f"bash -n failed on {mod_cmd}: {res.stderr}")

    def test_trivial_shell_pipelines_quoted_nl_and_commit_args_not_rewritten(self):
        """Trivial bash pipelines, quoted \\n print literals, and git commit strings stay un-rewritten."""
        from harness.hooks.command_safety_hook import check_inline_script_hygiene, sanitize_command

        safe_cmds = [
            "bash -c 'cd /tmp && head -n 5 foo.txt'",
            "bash -c \"cd /tmp &&\\\nhead -n 5 foo.txt\"",
            "bash -c 'rg pattern src/ | tail -n 10'",
            'python3 -c \'print("line1\\nline2")\'',
            'git commit -m "Fix python3 -c \\"import a\\nprint(1)\\""',
        ]
        for cmd in safe_cmds:
            dec, rsn = check_inline_script_hygiene(cmd)
            self.assertEqual(dec, "allow", f"Should allow without rewrite: {cmd} -> {rsn}")
            dec2, mod2, _ = sanitize_command(cmd)
            self.assertEqual(dec2, "allow")
            if mod2 is not None:
                self.assertNotIn("/scratch/exec_", mod2)

    def test_fence_exemption_for_workspace_scratch_paths(self):
        """Shell mutations targeting workspace scratch/ or .agents/scratch/ do not trigger code_dirty."""
        from harness.hooks.fence_tasks import check_shell_command_mutation

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws, state_dir = root / "ws", root / "state"
            ws.mkdir()
            for cmd in (
                "echo 'x=1' > scratch/tmp.py",
                "echo 'x=1' > .agents/scratch/exec_12345678.py",
            ):
                mutated = check_shell_command_mutation(cmd, cwd=ws, conv_id="c-scratch", state_dir=state_dir)
                self.assertFalse(mutated, f"Scratch write must remain exempt: {cmd}")


if __name__ == "__main__":
    unittest.main()
