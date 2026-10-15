#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Base infrastructure for Opaque-Box E2E Testing Track (Issues #41-#46).
Provides clean-room workspace sandboxing, CLI & hook invocation wrappers,
environment variable scrubbing, and fixture creation utilities.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple
import unittest
from unittest.mock import patch

from harness.cli import main as cli_main
from harness.delivery.constants import REPO_ROOT
from harness.hooks.runner import run_hook as runner_run_hook


class OpaqueBoxTestCase(unittest.TestCase):
    """
    Base test case for requirement-driven opaque-box E2E tests.
    Exercises product strictly through public CLI entrypoints, lifecycle hooks,
    and observable side-effects.
    """

    maxDiff = None

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()

        # Scrub and isolate environment variables
        self.orig_env = os.environ.copy()
        self.state_dir = self.ws / ".state"
        self.config_dir = self.ws / ".config" / "agyis"
        self.data_dir = self.ws / ".local" / "share" / "agyis"

        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        os.environ["PSL_HARNESS_STATE_DIR"] = str(self.state_dir)
        os.environ["AGYIS_CONFIG_DIR"] = str(self.config_dir)
        os.environ["AGYIS_DATA_DIR"] = str(self.data_dir)
        os.environ.pop("PSL_CONFIG_DIR", None)
        os.environ.pop("PSL_DATA_DIR", None)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.orig_env)
        self.temp_dir.cleanup()

    def run_cli(
        self,
        args: List[str],
        prog: str = "agyis",
        env_overrides: Optional[Dict[str, str]] = None,
        stdin_input: Optional[str] = None,
    ) -> Tuple[int, str, str]:
        """
        Executes CLI in-process via harness.cli.main, capturing stdout and stderr.
        Guarantees hermetic execution in <0.05s.
        """
        saved_env = os.environ.copy()
        if env_overrides:
            os.environ.update(env_overrides)

        stdin_buf = io.StringIO(stdin_input or "")
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        try:
            with patch("sys.stdin", stdin_buf), patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
                try:
                    code = cli_main(args, prog=prog)
                except SystemExit as exc:
                    code = exc.code if isinstance(exc.code, int) else 0
        finally:
            os.environ.clear()
            os.environ.update(saved_env)

        return code, stdout_buf.getvalue(), stderr_buf.getvalue()

    def run_hook_cli(
        self,
        hook_name: str,
        payload: Dict[str, Any] | str,
        env_overrides: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, str, str]:
        """
        Executes a lifecycle hook via harness.hooks.runner capturing exit code,
        stdout, and stderr.
        """
        payload_str = json.dumps(payload) if isinstance(payload, dict) else (payload or "")
        saved_env = os.environ.copy()
        if env_overrides:
            os.environ.update(env_overrides)

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        old_stdout = sys.stdout
        old_stderr = sys.stderr
        old_stdin = sys.stdin

        try:
            sys.stdout = stdout_buf
            sys.stderr = stderr_buf
            sys.stdin = io.StringIO(payload_str)
            try:
                code = runner_run_hook(hook_name, payload_str=payload_str)
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 0
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            sys.stdin = old_stdin
            os.environ.clear()
            os.environ.update(saved_env)

        return code, stdout_buf.getvalue(), stderr_buf.getvalue()

    def run_hook(
        self,
        hook_name: str,
        payload: Dict[str, Any] | str,
        env_overrides: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Convenience wrapper executing a lifecycle hook and returning parsed JSON output.
        """
        code, out, _ = self.run_hook_cli(hook_name, payload, env_overrides=env_overrides)
        try:
            data = json.loads(out.strip()) if out.strip() else {}
        except json.JSONDecodeError:
            data = {"raw_output": out}
        return code, data

    def run_binary(
        self,
        binary_name: str,
        args: List[str],
        cwd: Optional[Path] = None,
        env_overrides: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, str, str]:
        """
        Executes CLI out-of-process via subprocess using the standalone launcher binary
        (./agyis or ./psl).
        """
        bin_path = REPO_ROOT / binary_name
        env = os.environ.copy()
        if env_overrides:
            env.update(env_overrides)

        cmd = [sys.executable, str(bin_path)] + args
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(cwd or REPO_ROOT),
            env=env,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def parse_json_stdout(self, stdout: str) -> Dict[str, Any]:
        """Asserts that stdout is strictly valid JSON with zero extraneous logging."""
        stdout_clean = stdout.strip()
        self.assertTrue(
            stdout_clean.startswith("{") or stdout_clean.startswith("["),
            f"Expected JSON payload on stdout, got:\n{stdout}",
        )
        try:
            return json.loads(stdout_clean)
        except json.JSONDecodeError as err:
            self.fail(f"Failed to decode stdout as JSON: {err}\nOutput was:\n{stdout}")

    def create_fixture(
        self,
        fixture_type: str,
        custom_rules: Optional[str] = None,
    ) -> Path:
        """
        Creates synthetic workspaces matching realistic engineering patterns.
        Types: 'coordination', 'cleanroom', 'scratch', 'polyglot', 'legacy_psl', 'empty'.
        """
        if fixture_type == "empty":
            return self.ws

        if fixture_type == "coordination":
            teamwork_dir = self.ws / ".agents" / "teamwork"
            ledger_dir = self.ws / ".agents" / "ledger"
            teamwork_dir.mkdir(parents=True, exist_ok=True)
            ledger_dir.mkdir(parents=True, exist_ok=True)

            (teamwork_dir / "progress.md").write_text("# Progress Ledger\n- Task 1: Complete\n", encoding="utf-8")
            (teamwork_dir / "DISPATCH.md").write_text("# Dispatch Manifest\nTarget: Worker\n", encoding="utf-8")
            (teamwork_dir / "BRIEFING.md").write_text("# Briefing Manifest\nContext\n", encoding="utf-8")
            (teamwork_dir / "handoff.md").write_text("# Handoff\nDone\n", encoding="utf-8")
            (teamwork_dir / "task.md").write_text("# Task\nExecute\n", encoding="utf-8")
            (ledger_dir / "obligations.json").write_text(
                json.dumps({"obligations": [{"id": "ob_1", "status": "pending"}]}, indent=2),
                encoding="utf-8",
            )
            return self.ws

        if fixture_type == "cleanroom":
            specs_dir = self.ws / "docs" / "specs"
            ledger_dir = self.ws / ".agents" / "ledger"
            specs_dir.mkdir(parents=True, exist_ok=True)
            ledger_dir.mkdir(parents=True, exist_ok=True)

            (specs_dir / "hardware.md").write_text(
                "# Hardware Architecture Spec\nRegister 0x00: Control\n", encoding="utf-8"
            )
            (ledger_dir / "obligations.json").write_text(
                json.dumps({"obligations": [{"id": "req_1", "status": "draft"}]}, indent=2),
                encoding="utf-8",
            )
            return self.ws

        if fixture_type == "scratch":
            brain_scratch = self.ws / ".gemini" / "antigravity" / "brain" / "session_1" / "scratch"
            brain_scratch.mkdir(parents=True, exist_ok=True)
            script_file = brain_scratch / "script.py"
            script_file.write_text("print('scratch diagnostic')\n", encoding="utf-8")
            return self.ws

        if fixture_type == "polyglot":
            (self.ws / "package.json").write_text(
                json.dumps({"name": "polyglot-node", "scripts": {"test": "vitest run"}}, indent=2),
                encoding="utf-8",
            )
            (self.ws / "pyproject.toml").write_text(
                "[project]\nname='polyglot-py'\n[tool.pytest.ini_options]\ntestpaths=['tests']\n",
                encoding="utf-8",
            )
            (self.ws / "Makefile").write_text("test:\n\tpytest\n", encoding="utf-8")
            return self.ws

        if fixture_type == "legacy_psl":
            agent_dir = self.ws / ".agent"
            (agent_dir / "agents").mkdir(parents=True, exist_ok=True)
            (agent_dir / "workflows").mkdir(parents=True, exist_ok=True)
            (agent_dir / "rules").mkdir(parents=True, exist_ok=True)

            (agent_dir / "agents" / "code_reviewer.md").write_text(
                "# Code Reviewer\nExpert automated reviewer.", encoding="utf-8"
            )
            (agent_dir / "workflows" / "deploy_staging.md").write_text(
                "# Deploy Staging\n> Standard deploy runbook.\n\nDeploy commands.",
                encoding="utf-8",
            )
            (agent_dir / "rules" / "standards.md").write_text(
                "# Team Standards\nNever push broken builds.", encoding="utf-8"
            )

            rules_content = custom_rules or (
                "# Project Ground Rules\n- Fast reviews\n\n"
                "<!-- Added by PSL-HARNESS -->\nLegacy Invariants\n<!-- End PSL-HARNESS -->\n"
            )
            (self.ws / "AGENTS.md").write_text(rules_content, encoding="utf-8")
            return self.ws

        raise ValueError(f"Unknown fixture type: {fixture_type}")
