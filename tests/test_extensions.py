# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unit tests for Agyis Workspace CLI Extension Architecture (ADR-034).
Verifies extension discovery, manifest parsing, execution dispatch, and CLI auto-fallback.
"""

import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from harness.cli import main as cli_main
from harness.commands.ext import main as ext_main
from harness.runtime.extensions import (
    discover_workspace_commands,
    execute_extension_command,
    get_workspace_root,
)


class TestWorkspaceExtensions(unittest.TestCase):
    """Verifies workspace extension discovery and execution."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        (self.workspace / ".agents").mkdir(parents=True, exist_ok=True)
        self.cmd_dir = self.workspace / ".agents" / "commands"
        self.cmd_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_discover_commands_from_directory(self):
        # Create a Python command
        py_cmd = self.cmd_dir / "custom_task.py"
        py_cmd.write_text(
            '"""Custom Task Runner description."""\n'
            'import sys\n'
            'print("running custom task")\n',
            encoding="utf-8",
        )

        # Create a shell command
        sh_cmd = self.cmd_dir / "quick_backup.sh"
        sh_cmd.write_text(
            '#!/usr/bin/env bash\n'
            '# Quick Backup helper script\n'
            'echo "backing up"\n',
            encoding="utf-8",
        )

        cmds = discover_workspace_commands(self.workspace)
        self.assertIn("custom_task", cmds)
        self.assertIn("quick_backup", cmds)

        self.assertEqual(cmds["custom_task"].command_type, "python")
        self.assertIn("Custom Task Runner", cmds["custom_task"].description)
        self.assertEqual(cmds["custom_task"].origin, "file")

        self.assertEqual(cmds["quick_backup"].command_type, "shell")
        self.assertIn("Quick Backup helper", cmds["quick_backup"].description)

    def test_discover_commands_from_manifest(self):
        # Create a manifest
        manifest_file = self.workspace / ".agents" / "commands.json"
        script_file = self.workspace / "scripts" / "game_runner.py"
        script_file.parent.mkdir(parents=True, exist_ok=True)
        script_file.write_text('print("game running")\n', encoding="utf-8")

        manifest_data = {
            "game": {
                "entrypoint": "scripts/game_runner.py",
                "type": "python",
                "description": "Immortal automated game runner",
            }
        }
        manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

        cmds = discover_workspace_commands(self.workspace)
        self.assertIn("game", cmds)
        self.assertEqual(cmds["game"].command_type, "python")
        self.assertEqual(cmds["game"].description, "Immortal automated game runner")
        self.assertEqual(cmds["game"].origin, "manifest")

    def test_execute_python_extension_command(self):
        py_cmd = self.cmd_dir / "echo_test.py"
        out_file = self.workspace / "out.txt"
        py_cmd.write_text(
            f'import sys\n'
            f'with open("{out_file}", "w") as f:\n'
            f'    f.write(" ".join(sys.argv[1:]))\n',
            encoding="utf-8",
        )

        cmds = discover_workspace_commands(self.workspace)
        ret = execute_extension_command(cmds["echo_test"], ["arg1", "arg2"])
        self.assertEqual(ret, 0)
        self.assertTrue(out_file.is_file())
        self.assertEqual(out_file.read_text().strip(), "arg1 arg2")

    def test_ext_cli_list_and_init(self):
        # 1. Test ext init
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            ret = ext_main(["init", "my_bespoke_cmd", "--workspace", str(self.workspace)])
            self.assertEqual(ret, 0)

        created_file = self.cmd_dir / "my_bespoke_cmd.py"
        self.assertTrue(created_file.is_file())

        # 2. Test ext list
        buf_list = io.StringIO()
        with patch("sys.stdout", buf_list):
            ret = ext_main(["list", "--workspace", str(self.workspace), "--json"])
            self.assertEqual(ret, 0)
            data = json.loads(buf_list.getvalue())
            names = [item["name"] for item in data]
            self.assertIn("my_bespoke_cmd", names)

    def test_cli_main_fallback_dispatch(self):
        # Scaffold a command that writes an output file
        flag_file = self.workspace / "dispatched.flag"
        py_cmd = self.cmd_dir / "special_action.py"
        py_cmd.write_text(
            f'with open("{flag_file}", "w") as f:\n'
            f'    f.write("dispatched successfully")\n',
            encoding="utf-8",
        )

        # In current working directory of test, run ./agyis special_action
        with patch("os.getcwd", return_value=str(self.workspace)), \
             patch("sys.argv", ["agyis", "special_action"]):
            ret = cli_main(["special_action"])
            self.assertEqual(ret, 0)
            self.assertTrue(flag_file.is_file())
            self.assertEqual(flag_file.read_text().strip(), "dispatched successfully")

    def test_execute_extension_exports_adr034_env_and_preserves_pythonpath(self):
        from harness import __version__ as agyis_version

        py_cmd = self.cmd_dir / "env_probe.py"
        out_file = self.workspace / "env.json"
        py_cmd.write_text(
            f'import json, os\n'
            f'with open("{out_file}", "w", encoding="utf-8") as f:\n'
            f'    json.dump({{\n'
            f'        "AGYIS_WORKSPACE": os.environ.get("AGYIS_WORKSPACE"),\n'
            f'        "AGYIS_EXTENSION_COMMAND": os.environ.get("AGYIS_EXTENSION_COMMAND"),\n'
            f'        "WORKSPACE_ROOT": os.environ.get("WORKSPACE_ROOT"),\n'
            f'        "AGYIS_VERSION": os.environ.get("AGYIS_VERSION"),\n'
            f'        "PYTHONPATH": os.environ.get("PYTHONPATH"),\n'
            f'    }}, f)\n',
            encoding="utf-8",
        )

        cmds = discover_workspace_commands(self.workspace)
        with patch.dict(os.environ, {"PYTHONPATH": "/custom/lib/one"}):
            ret = execute_extension_command(cmds["env_probe"], [])
        self.assertEqual(ret, 0)
        data = json.loads(out_file.read_text(encoding="utf-8"))
        self.assertEqual(data["AGYIS_WORKSPACE"], str(self.workspace))
        self.assertEqual(data["WORKSPACE_ROOT"], str(self.workspace))
        self.assertEqual(data["AGYIS_EXTENSION_COMMAND"], "env_probe")
        self.assertEqual(data["AGYIS_VERSION"], agyis_version)
        pp_entries = data["PYTHONPATH"].split(os.pathsep)
        self.assertEqual(pp_entries[0], "/custom/lib/one")
        self.assertIn(str(self.workspace), pp_entries)

    def test_execute_extension_timeout_and_signal_handling(self):
        slow_cmd = self.cmd_dir / "slow_cmd.py"
        slow_cmd.write_text("import time\ntime.sleep(2.0)\n", encoding="utf-8")

        sig_cmd = self.cmd_dir / "sig_cmd.py"
        sig_cmd.write_text("import os, signal\nos.kill(os.getpid(), signal.SIGTERM)\n", encoding="utf-8")

        cmds = discover_workspace_commands(self.workspace)
        with patch("sys.stderr", new_callable=io.StringIO):
            timeout_rc = execute_extension_command(cmds["slow_cmd"], [], timeout=0.05)
        self.assertEqual(timeout_rc, 124)

        sig_rc = execute_extension_command(cmds["sig_cmd"], [], timeout=5.0)
        self.assertEqual(sig_rc, 143)


if __name__ == "__main__":
    unittest.main()
