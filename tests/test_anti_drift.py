#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Unit and integration contract tests for harness/hooks/anti_drift_hook.py (ADR-024).
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from harness.hooks.anti_drift_hook import (
    check_auditor_write_block,
    check_drift,
    check_ledger_cluster_tables,
    check_plan_mode_lock,
    find_active_plan,
    has_cluster_status_table,
    has_telemetry_proof,
    is_exempt_file,
    parse_plan_files,
    record_telemetry_proof,
)


class TestAntiDriftHook(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_plan_files_markdown_links(self):
        """Extracts files from markdown links with file:// and relative paths."""
        content = """
# Plan
[anti_drift_hook.py](file:///workspace/harness/hooks/anti_drift_hook.py#L1-L50)
[cli.py](harness/cli.py)
[External Docs](https://example.com/docs)
[Mail](mailto:dev@example.com)
"""
        files = parse_plan_files(content)
        self.assertIn("anti_drift_hook.py", files)
        self.assertIn("harness/hooks/anti_drift_hook.py", files)
        self.assertIn("cli.py", files)
        self.assertIn("harness/cli.py", files)
        self.assertNotIn("https://example.com/docs", files)
        self.assertNotIn("External Docs", files)

    def test_parse_plan_files_action_headers(self):
        """Extracts files declared in action headers ([MODIFY], [NEW], [DELETE])."""
        content = """
### Proposed Changes
#### [MODIFY] [harness/hooks/hooks.json](file:///workspace/harness/hooks/hooks.json)
#### [NEW] tests/test_anti_drift.py
#### [DELETE] legacy/obsolete_module.py
#### [CREATE] `src/pipeline.rs`
"""
        files = parse_plan_files(content)
        self.assertIn("hooks.json", files)
        self.assertIn("harness/hooks/hooks.json", files)
        self.assertIn("test_anti_drift.py", files)
        self.assertIn("tests/test_anti_drift.py", files)
        self.assertIn("obsolete_module.py", files)
        self.assertIn("legacy/obsolete_module.py", files)
        self.assertIn("pipeline.rs", files)
        self.assertIn("src/pipeline.rs", files)

    def test_parse_plan_files_backticks_and_exclusions(self):
        """Extracts backticked file paths while excluding tool names, commands, and numbers."""
        content = """
- Edit `harness/cli.py` to add `anti-drift`
- Update `package.json` and `pyproject.toml`
- Tool `write_to_file` and `run_command` should not be extracted
- Flags like `--strict` or version numbers like `3.12` or `1.0s` must be ignored
- Concepts like `ADR-024` or `API` or `None` must be ignored
- Single script `psl` should be captured
"""
        files = parse_plan_files(content)
        self.assertIn("harness/cli.py", files)
        self.assertIn("cli.py", files)
        self.assertIn("package.json", files)
        self.assertIn("pyproject.toml", files)
        self.assertIn("psl", files)

        self.assertNotIn("write_to_file", files)
        self.assertNotIn("run_command", files)
        self.assertNotIn("--strict", files)
        self.assertNotIn("3.12", files)
        self.assertNotIn("1.0s", files)
        self.assertNotIn("ADR-024", files)
        self.assertNotIn("API", files)
        self.assertNotIn("None", files)

    def test_parse_plan_empty_or_no_files(self):
        """Returns empty set for empty content or content with no file references."""
        self.assertEqual(parse_plan_files(""), set())
        self.assertEqual(parse_plan_files("Just a general note without code paths."), set())

    def test_is_exempt_file(self):
        """Exempts markdown, documentation, scratch, artifacts, and brain files."""
        self.assertTrue(is_exempt_file(""))
        self.assertTrue(is_exempt_file("README.md"))
        self.assertTrue(is_exempt_file("docs/official-specs/lifecycle-hooks.md"))
        self.assertTrue(is_exempt_file("notes.txt"))
        self.assertTrue(is_exempt_file("docs/index.rst"))
        self.assertTrue(is_exempt_file(".agents/artifacts/plan.md"))
        self.assertTrue(is_exempt_file(".agents/artifacts/metadata.json"))
        self.assertTrue(is_exempt_file("scratch/scratch_test.py"))
        self.assertTrue(is_exempt_file("/tmp/tempfile.py"))
        self.assertTrue(is_exempt_file("tmp/experiment.sh"))
        self.assertTrue(is_exempt_file("/home/user/.gemini/antigravity/brain/session123/artifact.json"))

        # Non-exempt code files
        self.assertFalse(is_exempt_file("harness/cli.py"))
        self.assertFalse(is_exempt_file("tests/test_anti_drift.py"))
        self.assertFalse(is_exempt_file("src/main.ts"))
        self.assertFalse(is_exempt_file("lib.rs"))

    def test_check_drift_matching(self):
        """Permits modifications when target matches declared plan files."""
        plan_files = {
            "harness/hooks/anti_drift_hook.py",
            "anti_drift_hook.py",
            "tests/test_anti_drift.py",
            "test_anti_drift.py",
        }

        # Exact match
        res1 = check_drift("harness/hooks/anti_drift_hook.py", plan_files)
        self.assertEqual(res1["decision"], "allow")

        # Absolute path suffix match
        res2 = check_drift("/workspace/kuasha/harness/hooks/anti_drift_hook.py", plan_files)
        self.assertEqual(res2["decision"], "allow")

        # Basename match
        res3 = check_drift("other/path/to/test_anti_drift.py", plan_files)
        self.assertEqual(res3["decision"], "allow")

    def test_check_drift_exempt_always_allowed(self):
        """Permits modifications to exempt files regardless of plan files."""
        plan_files = {"harness/hooks/anti_drift_hook.py"}

        res = check_drift("docs/official-specs/lifecycle-hooks.md", plan_files, strict=True)
        self.assertEqual(res["decision"], "allow")

        res_scratch = check_drift("scratch/test.py", plan_files, strict=True)
        self.assertEqual(res_scratch["decision"], "allow")

    def test_check_drift_empty_plan_allowed(self):
        """Permits modifications when plan has no declared files (unconstrained)."""
        res = check_drift("harness/cli.py", set(), strict=True)
        self.assertEqual(res["decision"], "allow")

    def test_check_drift_non_strict_mode(self):
        """Emits allow with notice when undeclared file is edited in non-strict mode."""
        plan_files = {"harness/hooks/anti_drift_hook.py"}
        target = "harness/cli.py"

        res = check_drift(target, plan_files, strict=False)
        self.assertEqual(res["decision"], "allow")
        self.assertIn("PSL Anti-Drift Notice", res["reason"])
        self.assertIn(target, res["reason"])
        self.assertIn("permitted under non-strict mode", res["reason"])

    def test_check_drift_strict_mode(self):
        """Emits ask gate when undeclared file is edited in strict mode."""
        plan_files = {"harness/hooks/anti_drift_hook.py"}
        target = "harness/cli.py"

        # Via strict argument
        res_arg = check_drift(target, plan_files, strict=True)
        self.assertEqual(res_arg["decision"], "ask")
        self.assertIn("PSL Anti-Drift Gate", res_arg["reason"])
        self.assertIn(target, res_arg["reason"])
        self.assertIn("Please confirm intentional edit", res_arg["reason"])

        # Via PSL_STRICT_ANTI_DRIFT environment variable
        os.environ["PSL_STRICT_ANTI_DRIFT"] = "1"
        try:
            res_env = check_drift(target, plan_files, strict=False)
            self.assertEqual(res_env["decision"], "ask")
            self.assertIn("PSL Anti-Drift Gate", res_env["reason"])
        finally:
            del os.environ["PSL_STRICT_ANTI_DRIFT"]

    def test_find_active_plan(self):
        """Discovers implementation plans from env override, workspace root, or cwd."""
        # 1. Env override
        override_file = self.workspace / "custom_plan.md"
        override_file.write_text("# Custom Plan", encoding="utf-8")
        os.environ["PSL_PLAN_PATH"] = str(override_file)
        try:
            found = find_active_plan()
            self.assertEqual(found, override_file)
        finally:
            del os.environ["PSL_PLAN_PATH"]

        # 2. Workspace root (.agents/artifacts/implementation_plan.md)
        artifacts_dir = self.workspace / ".agents" / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        ws_plan = artifacts_dir / "implementation_plan.md"
        ws_plan.write_text("# Workspace Plan", encoding="utf-8")

        found = find_active_plan(workspace_root=self.workspace)
        self.assertEqual(found, ws_plan)

        # 3. None when missing
        empty_dir = self.workspace / "empty"
        empty_dir.mkdir()
        found = find_active_plan(workspace_root=empty_dir)
        self.assertIsNone(found)

    def test_cli_hook_contract_allow(self):
        """CLI hook consumes protojson and allows declared edits."""
        import io
        from unittest.mock import patch
        from harness.hooks import anti_drift_hook

        plan_file = self.workspace / "implementation_plan.md"
        plan_file.write_text("### Proposed Changes\n- `harness/hooks/anti_drift_hook.py`\n", encoding="utf-8")

        payload = {
            "conversationId": "drift-test-1",
            "workspacePaths": [str(self.workspace)],
            "toolCall": {
                "name": "replace_file_content",
                "args": {
                    "TargetFile": str(self.workspace / "harness/hooks/anti_drift_hook.py"),
                },
            },
        }

        buf = io.StringIO()
        with patch.dict(os.environ, {"PSL_PLAN_PATH": str(plan_file)}), \
             patch("sys.stdin", io.StringIO(json.dumps(payload))), \
             patch("sys.stdout", buf):
            anti_drift_hook.main()

        res = json.loads(buf.getvalue().strip())
        self.assertEqual(res["decision"], "allow")

    def test_cli_hook_contract_strict_ask(self):
        """CLI hook blocks undeclared edits in strict mode by asking operator."""
        import io
        from unittest.mock import patch
        from harness.hooks import anti_drift_hook

        plan_file = self.workspace / "implementation_plan.md"
        plan_file.write_text("### Proposed Changes\n- `harness/hooks/anti_drift_hook.py`\n", encoding="utf-8")

        payload = {
            "conversationId": "drift-test-2",
            "workspacePaths": [str(self.workspace)],
            "toolCall": {
                "name": "write_to_file",
                "args": {
                    "TargetFile": "/workspace/unapproved/secret.py",
                },
            },
        }

        buf = io.StringIO()
        with patch.dict(os.environ, {"PSL_PLAN_PATH": str(plan_file), "PSL_STRICT_ANTI_DRIFT": "1"}), \
             patch("sys.stdin", io.StringIO(json.dumps(payload))), \
             patch("sys.stdout", buf):
            anti_drift_hook.main()

        res = json.loads(buf.getvalue().strip())
        self.assertEqual(res["decision"], "ask")
        self.assertIn("PSL Anti-Drift Gate", res["reason"])

    def test_cli_hook_action_api(self):
        """CLI hook handles action=check_drift direct API payload."""
        import io
        from unittest.mock import patch
        from harness.hooks import anti_drift_hook

        payload = {
            "action": "check_drift",
            "target_file": "undeclared.py",
            "plan_files": ["main.py"],
            "strict": True,
        }
        buf = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), \
             patch("sys.stdout", buf):
            anti_drift_hook.main()

        res = json.loads(buf.getvalue().strip())
        self.assertEqual(res["decision"], "ask")


    def test_find_active_plan_generic_glob(self):
        """Discovers generic *plan*.md in workspace root via glob fallback."""
        generic_plan = self.workspace / "phase_4_refactor_plan.md"
        generic_plan.write_text("# Generic Plan", encoding="utf-8")
        found = find_active_plan(workspace_root=self.workspace)
        self.assertEqual(found, generic_plan)

    def test_parse_plan_files_parentheses_stripping(self):
        """Strips enclosing or trailing parentheses from header file tokens."""
        content = """
### Tasks
#### [MODIFY] (harness/hooks/anti_drift_hook.py)
#### [NEW] src/feature.py)
"""
        files = parse_plan_files(content)
        self.assertIn("harness/hooks/anti_drift_hook.py", files)
        self.assertIn("src/feature.py", files)

    def test_cli_hook_plan_read_oserror(self):
        """CLI hook safely allows on OSError reading plan file."""
        import io
        from unittest.mock import patch, MagicMock
        from harness.hooks.anti_drift_hook import main

        payload = {
            "conversationId": "test-oserr",
            "workspacePaths": [str(self.workspace)],
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "src/app.py"},
            },
        }
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("harness.hooks.anti_drift_hook.find_active_plan") as mock_find:
            mock_path = MagicMock()
            mock_path.is_file.return_value = True
            mock_path.read_text.side_effect = OSError("Disk read error")
            mock_find.return_value = mock_path
            main()
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")

    def test_cli_hook_parse_plan_error_logs_stderr(self):
        """CLI hook logs unexpected parsing errors to stderr and allows."""
        import io
        from unittest.mock import patch, MagicMock
        from harness.hooks.anti_drift_hook import main

        payload = {
            "conversationId": "test-parse-err",
            "workspacePaths": [str(self.workspace)],
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "src/app.py"},
            },
        }
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err, \
             patch("harness.hooks.anti_drift_hook.find_active_plan") as mock_find, \
             patch("harness.hooks.anti_drift_hook.parse_plan_files") as mock_parse:
            mock_path = MagicMock()
            mock_path.is_file.return_value = True
            mock_path.read_text.return_value = "plan content"
            mock_find.return_value = mock_path
            mock_parse.side_effect = RuntimeError("Parser exploded")
            main()
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")
            self.assertIn("PSL Anti-Drift: Error parsing plan files", mock_err.getvalue())
            self.assertIn("Parser exploded", mock_err.getvalue())

    def test_cli_hook_malformed_json_returns_allow(self):
        """CLI hook safely allows on malformed JSON payload."""
        import io
        from unittest.mock import patch
        from harness.hooks.anti_drift_hook import main

        with patch("sys.stdin", io.StringIO("invalid-json{{{")), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            main()
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")

    def test_auditor_write_block_direct(self):
        """Auditor write guard blocks file mutation tools directly."""
        for tool in ("write_to_file", "replace_file_content", "edit_file"):
            for role in ("auditor", "harness_auditor", "qa_verifier"):
                payload = {
                    "role": role,
                    "toolCall": {"name": tool, "args": {"TargetFile": "src/app.py"}},
                }
                res = check_auditor_write_block(payload)
                self.assertIsNotNone(res, f"Expected block for {role} using {tool}")
                self.assertEqual(res["decision"], "deny")
                self.assertIn("PSL Auditor Invariant", res["reason"])

    def test_auditor_allowed_for_read_and_exec(self):
        """Auditor write guard allows read and execution tools."""
        for tool in ("run_command", "view_file", "list_dir", "grep_search"):
            payload = {
                "role": "harness_auditor",
                "toolCall": {"name": tool, "args": {"CommandLine": "./psl test"}},
            }
            res = check_auditor_write_block(payload)
            self.assertIsNone(res, f"Expected allow for auditor using {tool}")

    def test_non_auditor_not_blocked_by_auditor_guard(self):
        """Non-auditor agents (builder, implementer) are not blocked by auditor guard."""
        payload = {
            "role": "harness_builder",
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": "src/app.py"}},
        }
        res = check_auditor_write_block(payload)
        self.assertIsNone(res)

    def test_auditor_write_block_via_env_var(self):
        """Auditor role via PSL_SUBAGENT_ROLE environment variable blocks file mutations."""
        with patch.dict(os.environ, {"PSL_SUBAGENT_ROLE": "auditor"}):
            payload = {
                "toolCall": {"name": "write_to_file", "args": {"TargetFile": "src/app.py"}},
            }
            res = check_auditor_write_block(payload)
            self.assertIsNotNone(res)
            self.assertEqual(res["decision"], "deny")

    def test_cli_hook_main_auditor_write_block(self):
        """main() intercepts auditor file mutation and outputs block response."""
        import io
        from unittest.mock import patch
        from harness.hooks.anti_drift_hook import main

        payload = {
            "role": "harness_auditor",
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "src/app.py", "CodeContent": "bad"},
            },
        }
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            main()
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "deny")
            self.assertIn("PSL Auditor Invariant", res["reason"])

    def test_anti_drift_auditor_block(self):
        """
        Asserts that harness_auditor write attempts (across write_to_file,
        replace_file_content, edit_file) are rejected programmatically with
        zero interactive operator prompts.
        """
        from harness.hooks.anti_drift_hook import main

        write_tools = [
            ("write_to_file", {"TargetFile": "src/module.py", "CodeContent": "evil"}),
            ("replace_file_content", {"TargetFile": "src/module.py", "TargetContent": "a", "ReplacementContent": "b"}),
            ("edit_file", {"FilePath": "src/module.py", "content": "mutated"}),
        ]

        for tool_name, args in write_tools:
            # 1. Direct function check
            payload = {
                "role": "harness_auditor",
                "toolCall": {"name": tool_name, "args": args},
            }
            res = check_auditor_write_block(payload)
            self.assertIsNotNone(res)
            self.assertEqual(res["decision"], "deny")
            self.assertIn("PSL Auditor Invariant", res["reason"])

            # 2. End-to-end hook main() execution (programmatic, zero prompt)
            with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                main()
                stdout_val = mock_out.getvalue().strip()
                res_main = json.loads(stdout_val)
                self.assertEqual(res_main["decision"], "deny")
                self.assertIn("PSL Auditor Invariant", res_main["reason"])

            # 3. Environment variable fallback (PSL_SUBAGENT_ROLE)
            payload_env = {
                "toolCall": {"name": tool_name, "args": args},
            }
            with patch.dict(os.environ, {"PSL_SUBAGENT_ROLE": "harness_auditor"}):
                with patch("sys.stdin", io.StringIO(json.dumps(payload_env))), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                    main()
                    res_env = json.loads(mock_out.getvalue().strip())
                    self.assertEqual(res_env["decision"], "deny")
                    self.assertIn("PSL Auditor Invariant", res_env["reason"])

    def test_planner_and_coordinator_write_block(self):
        """Planner and coordinator subagents are blocked from mutating files."""
        for role in ("planner", "architect", "coordinator", "orchestrator"):
            payload = {
                "role": role,
                "toolCall": {
                    "name": "replace_file_content",
                    "args": {"TargetFile": "src/app.py"},
                },
            }
            res = check_auditor_write_block(payload)
            self.assertIsNotNone(res, f"Expected block for {role}")
            self.assertEqual(res["decision"], "deny")
            self.assertIn("PSL Write-Block Guard", res["reason"])

    def test_planner_write_blocked_for_code_files(self):
        """Planner cannot mutate code files directly."""
        for role in ("planner", "architect"):
            payload = {
                "role": role,
                "toolCall": {
                    "name": "write_to_file",
                    "args": {"TargetFile": "src/app.py", "CodeContent": "print(1)"},
                },
            }
            res = check_auditor_write_block(payload)
            self.assertIsNotNone(res)
            self.assertEqual(res["decision"], "deny")
            self.assertIn("is artifact-only and cannot mutate code files directly", res["reason"])

    def test_planner_write_allowed_for_exempt_artifact_files(self):
        """Planner can write to exempt artifact files for synthesis."""
        exempt_paths = [
            ".agents/artifacts/plan.md",
            "/brain/test/plan.md",
            "scratch/notes.txt",
        ]
        for role in ("planner", "architect", "coordinator", "orchestrator"):
            for path in exempt_paths:
                payload = {
                    "role": role,
                    "toolCall": {
                        "name": "write_to_file",
                        "args": {"TargetFile": path, "CodeContent": "# Plan"},
                    },
                }
                res = check_auditor_write_block(payload)
                self.assertIsNone(res, f"Expected planner write to be allowed for exempt path: {path}")

    def test_explicit_write_false_block(self):
        """Any agent with write: false or permissions: {write: false} is blocked from mutating files."""
        payload1 = {
            "role": "custom_agent",
            "write": False,
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": "src/app.py"}},
        }
        res1 = check_auditor_write_block(payload1)
        self.assertIsNotNone(res1)
        self.assertEqual(res1["decision"], "deny")

        payload2 = {
            "role": "custom_agent_2",
            "permissions": {"write": False},
            "toolCall": {"name": "replace_file_content", "args": {"TargetFile": "src/app.py"}},
        }
        res2 = check_auditor_write_block(payload2)
        self.assertIsNotNone(res2)
        self.assertEqual(res2["decision"], "deny")

    def test_custodian_write_block(self):
        """Custodian role is blocked from mutating files with custodian invariant reason."""
        for role in ("custodian", "harness_custodian", "git_custodian", "commit_gate", "subagent_x_custodian"):
            payload = {
                "role": role,
                "toolCall": {
                    "name": "write_to_file",
                    "args": {"TargetFile": "src/app.py", "CodeContent": "bad"},
                },
            }
            res = check_auditor_write_block(payload)
            self.assertIsNotNone(res, f"Expected block for {role}")
            self.assertEqual(res["decision"], "deny")
            self.assertIn("PSL Custodian Invariant", res["reason"])

    def test_main_and_lead_not_blocked(self):
        """Main and lead agents are permitted to mutate files when explicit_write_false is not set."""
        for role in ("main", "psl_main", "lead", "PSL Lead Architect & Master Implementer"):
            payload = {
                "role": role,
                "toolCall": {
                    "name": "write_to_file",
                    "args": {"TargetFile": "src/app.py"},
                },
            }
            res = check_auditor_write_block(payload)
            self.assertIsNone(res, f"Expected no block for {role}")

    def test_plan_mode_blocks_code_mutations(self):
        """When in plan mode, code file modifications are blocked (ADR-031)."""
        payload = {
            "mode": "plan",
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "harness/core.py", "CodeContent": "x = 1"},
            },
        }
        res = check_plan_mode_lock(payload)
        self.assertIsNotNone(res)
        self.assertEqual(res["decision"], "deny")
        self.assertIn("PSL Native Plan-Mode Lock", res["reason"])

    def test_plan_mode_allows_exempt_files(self):
        """When in plan mode, documentation and artifacts remain editable."""
        for exempt_path in (
            ".agents/artifacts/implementation_plan.md",
            "docs/official-specs/spec.md",
            "scratch/notes.py",
        ):
            payload = {
                "mode": "plan",
                "toolCall": {
                    "name": "write_to_file",
                    "args": {"TargetFile": exempt_path, "CodeContent": "doc"},
                },
            }
            res = check_plan_mode_lock(payload)
            self.assertIsNone(res, f"Expected exempt edit for {exempt_path}")

    def test_plan_mode_inactive_allows_flow(self):
        """When mode is default or not plan, check_plan_mode_lock returns None."""
        payload = {
            "mode": "default",
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "src/app.py"},
            },
        }
        self.assertIsNone(check_plan_mode_lock(payload))

    def test_has_cluster_status_table_detection(self):
        """Verifies cluster table detection matches node/metric tables and ignores unrelated text."""
        cluster_table_content = """
## 🗺️ Active Tasks & Strand Allocation Matrix

| Node | Hardware Role | Assigned Task | Branch | Elapsed | Telemetry Cadence |
| :--- | :--- | :--- | :--- | :---: | :---: |
| `@desktop` | Anchor / Coordinator | Orchestrating Campaign | `main` | 4h 12m | 120s |
| `@laptop` | CUDA Inference | Task #3 | `feat/cuda` | 1h 45m | Quarantined |
"""
        self.assertTrue(has_cluster_status_table(cluster_table_content))

        quota_table_content = """
## 🔋 Fleet Token Quota Snapshot

| Node | Active Profile | 5-Hour Quota Remaining | Weekly Quota Remaining | Keyring State |
| :--- | :--- | :---: | :---: | :---: |
| `@desktop` | `primary` | 82% | 91% | Unlocked |
"""
        self.assertTrue(has_cluster_status_table(quota_table_content))

        unrelated_table = """
| Parameter | Type | Description |
| :--- | :--- | :--- |
| timeout | int | Seconds to wait |
"""
        self.assertFalse(has_cluster_status_table(unrelated_table))

        no_table_content = """
## 📈 Milestones & PR Lifecycle Tracker
- [x] Milestone 1 complete
- [ ] Milestone 2 in progress
"""
        self.assertFalse(has_cluster_status_table(no_table_content))

    def test_operator_ledger_unverified_cluster_table_denied(self):
        """Writing cluster tables to operator_ledger.md without live telemetry proof is denied."""
        cluster_content = """
| Node | Hardware Role | Status |
| :--- | :--- | :--- |
| @desktop | Anchor | ACTIVE |
"""
        res = check_ledger_cluster_tables(
            "operator_ledger.md",
            cluster_content,
            conv_id="test-ledger-deny",
            state_dir=self.workspace,
        )
        self.assertIsNotNone(res)
        self.assertEqual(res["decision"], "deny")
        self.assertIn("PSL Anti-Drift Gate", res["reason"])
        self.assertIn("knot ledger generate --json", res["reason"])

    def test_operator_ledger_with_telemetry_proof_allowed(self):
        """Writing cluster tables to operator_ledger.md with live telemetry proof is allowed."""
        conv_id = "test-ledger-allow"
        cluster_content = """
| Node | Hardware Role | Status |
| :--- | :--- | :--- |
| @desktop | Anchor | ACTIVE |
"""
        # Record proof
        ok = record_telemetry_proof("knot status --json", conv_id=conv_id, state_dir=self.workspace)
        self.assertTrue(ok)
        self.assertTrue(has_telemetry_proof(conv_id=conv_id, state_dir=self.workspace))

        res = check_ledger_cluster_tables(
            "operator_ledger.md",
            cluster_content,
            conv_id=conv_id,
            state_dir=self.workspace,
        )
    def test_record_telemetry_proof_oserror_handling(self):
        """record_telemetry_proof returns False and logs to stderr on OSError (DEFECT-L3-02)."""
        conv_id = "test-oserror-handling"
        stderr_buf = io.StringIO()
        with patch("pathlib.Path.write_text", side_effect=OSError("Disk full")), patch("sys.stderr", stderr_buf):
            ok = record_telemetry_proof("knot status --json", conv_id=conv_id, state_dir=self.workspace)
        self.assertFalse(ok)
        self.assertIn("PSL Anti-Drift: Failed to record telemetry proof: Disk full", stderr_buf.getvalue())

    def test_operator_ledger_without_cluster_tables_allowed(self):
        """Updating operator_ledger.md with notes/milestones (no cluster tables) is allowed without proof."""
        notes_content = """
# Operator Ledger
## Milestones
- [x] Step 1 finished
"""
        res = check_ledger_cluster_tables(
            "operator_ledger.md",
            notes_content,
            conv_id="test-ledger-notes",
            state_dir=self.workspace,
        )
        self.assertIsNone(res)

    def test_cli_hook_operator_ledger_contract(self):
        """Contract test: main() blocks unverified cluster table writes on operator_ledger.md."""
        import io
        from harness.hooks import anti_drift_hook

        cluster_content = """
| Node | Status | Quota |
| :--- | :--- | :--- |
| @laptop | ONLINE | 80% |
"""
        payload = {
            "conversationId": "cli-ledger-conv",
            "toolCall": {
                "name": "write_to_file",
                "args": {
                    "TargetFile": "/path/to/operator_ledger.md",
                    "CodeContent": cluster_content,
                },
            },
        }

        with patch.dict(os.environ, {"PSL_HARNESS_STATE_DIR": str(self.workspace)}):
            # 1. Unverified attempt is denied
            buf1 = io.StringIO()
            with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", buf1):
                anti_drift_hook.main()

            res1 = json.loads(buf1.getvalue().strip())
            self.assertEqual(res1["decision"], "deny")
            self.assertIn("PSL Anti-Drift Gate", res1["reason"])

            # 2. Record proof via run_command toolCall
            proof_payload = {
                "conversationId": "cli-ledger-conv",
                "toolCall": {
                    "name": "run_command",
                    "args": {"CommandLine": "knot ledger generate --json"},
                },
            }
            buf2 = io.StringIO()
            with patch("sys.stdin", io.StringIO(json.dumps(proof_payload))), patch("sys.stdout", buf2):
                anti_drift_hook.main()

            # 3. Now write is allowed
            buf3 = io.StringIO()
            with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", buf3):
                anti_drift_hook.main()

            res3 = json.loads(buf3.getvalue().strip())
            self.assertEqual(res3["decision"], "allow")


if __name__ == "__main__":
    unittest.main()
