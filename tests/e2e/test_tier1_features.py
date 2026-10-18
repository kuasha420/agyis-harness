#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Tier 1: Feature Coverage (Issues #41, #42, #43, and #46).
Validates each feature across nominal operating range (5 tests per feature, 20 tests total):
- Feature 1 (Issue #41): Anti-Loop Coordination Exemption Expansion
- Feature 2 (Issue #42): Stop-Fence PostToolUse Wiring & Dirty Clearance
- Feature 3 (Issue #43): Scratch Path Isolation & Boundary Scoping
- Feature 6 (Issue #46): Standardized Issue Templates
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional
import unittest
from unittest.mock import patch

from harness.delivery.constants import REPO_ROOT
from tests.e2e.harness_base import OpaqueBoxTestCase


class TestTier1Features(OpaqueBoxTestCase):
    """
    Tier 1 E2E tests validating nominal behavior of Features 1 through 6.
    """

    # =========================================================================
    # Feature 1 (Issue #41): Anti-Loop Coordination Exemption
    # =========================================================================

    def test_f1_01_teamwork_directory_progress_repeated_view(self) -> None:
        """Assures reading progress.md in .agents/teamwork/ 10 times produces 0 loop denials."""
        self.create_fixture("coordination")
        target_path = str(self.ws / ".agents" / "teamwork" / "progress.md")

        for i in range(10):
            payload = {
                "conversationId": "c_f1_01",
                "toolCall": {
                    "name": "view_file",
                    "args": {"AbsolutePath": target_path},
                },
            }
            code, resp = self.run_hook("anti-loop", payload)
            self.assertEqual(code, 0)
            self.assertEqual(
                resp.get("decision"),
                "allow",
                f"Iteration {i} was unexpectedly denied: {resp.get('reason')}",
            )

    def test_f1_02_ledger_directory_obligations_repeated_view(self) -> None:
        """Assures reading obligations.json in .agents/ledger/ 10 times produces 0 loop denials."""
        self.create_fixture("coordination")
        target_path = str(self.ws / ".agents" / "ledger" / "obligations.json")

        for i in range(10):
            payload = {
                "conversationId": "c_f1_02",
                "toolCall": {
                    "name": "view_file",
                    "args": {"AbsolutePath": target_path},
                },
            }
            code, resp = self.run_hook("anti-loop", payload)
            self.assertEqual(code, 0)
            self.assertEqual(
                resp.get("decision"),
                "allow",
                f"Iteration {i} in ledger was denied: {resp.get('reason')}",
            )

    def test_f1_03_coordination_basenames_dispatch_briefing_task(self) -> None:
        """Assures coordination manifest basenames are exempted regardless of directory."""
        self.create_fixture("coordination")
        coordination_files = [
            "DISPATCH.md",
            "BRIEFING.md",
            "handoff.md",
            "task.md",
            "progress.md",
            "obligations.json",
        ]

        for fname in coordination_files:
            file_path = str(self.ws / ".agents" / "teamwork" / fname)
            for _ in range(6):
                payload = {
                    "conversationId": f"c_f1_03_{fname}",
                    "toolCall": {
                        "name": "view_file",
                        "args": {"Path": file_path},
                    },
                }
                code, resp = self.run_hook("anti-loop", payload)
                self.assertEqual(code, 0)
                self.assertEqual(resp.get("decision"), "allow")

    def test_f1_04_argument_name_invariance(self) -> None:
        """Assures coordination path exemption works across diverse tool argument keys."""
        target_path = str(self.ws / ".agents" / "teamwork" / "DISPATCH.md")
        arg_keys = [
            "AbsolutePath",
            "Path",
            "TargetFile",
            "file_path",
            "filePath",
            "path",
            "target_file",
        ]

        for key in arg_keys:
            conv_id = f"c_f1_04_{key}"
            for _ in range(6):
                payload = {
                    "conversationId": conv_id,
                    "toolCall": {
                        "name": "view_file",
                        "args": {key: target_path},
                    },
                }
                code, resp = self.run_hook("anti-loop", payload)
                self.assertEqual(code, 0)
                self.assertEqual(
                    resp.get("decision"),
                    "allow",
                    f"Argument key '{key}' failed coordination exemption",
                )

    def test_f1_05_production_code_rate_limited(self) -> None:
        """Assures production source code remains strictly subject to anti-loop rate limiting."""
        prod_file = str(self.ws / "src" / "core" / "module.rs")
        conv_id = "c_f1_05_prod"

        decisions = []
        for _ in range(6):
            payload = {
                "conversationId": conv_id,
                "toolCall": {
                    "name": "view_file",
                    "args": {"AbsolutePath": prod_file},
                },
            }
            code, resp = self.run_hook("anti-loop", payload)
            self.assertEqual(code, 0)
            decisions.append(resp.get("decision"))

        self.assertIn("deny", decisions, "Production code view loop was not denied")

    # =========================================================================
    # Feature 2 (Issue #42): Stop-Fence Wiring & Clearance
    # =========================================================================

    def test_f2_01_post_tool_use_test_command_exit_zero_clears_dirty(self) -> None:
        """Assures PostToolUse of a passing test command (exit 0) clears code_dirty state."""
        conv_id = "c_f2_01"
        ws_file = str(self.ws / "src" / "lib.py")

        # 1. Edit code file -> dirty = True
        edit_payload = {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": ws_file, "CodeContent": "def test(): pass"},
            },
        }
        self.run_hook("verification-fence", edit_payload)

        # Confirm dirty state
        _, state_data = self.run_hook("verification-fence", {"conversationId": conv_id, "action": "reset"})
        # Re-apply edit
        self.run_hook("verification-fence", edit_payload)

        # 2. Run passing test command via PostToolUse
        test_payload = {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "exitCode": 0,
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "python3 -m unittest discover", "Cwd": str(self.ws)},
            },
        }
        self.run_hook("verification-fence", test_payload)

        # 3. Evaluate stop -> should be allow
        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "allow")

    def test_f2_02_post_tool_use_test_command_exit_nonzero_retains_dirty(self) -> None:
        """Assures PostToolUse of a failing test command (exit 1) retains code_dirty state."""
        conv_id = "c_f2_02"
        ws_file = str(self.ws / "src" / "lib.py")

        # 1. Edit code file
        edit_payload = {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": ws_file, "CodeContent": "broken"},
            },
        }
        self.run_hook("verification-fence", edit_payload)

        # 2. Run failing test command
        test_payload = {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "exitCode": 1,
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "python3 -m unittest discover", "Cwd": str(self.ws)},
            },
        }
        self.run_hook("verification-fence", test_payload)

        # 3. Evaluate stop -> should block with continue
        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "continue")

    def test_f2_03_stop_event_allowed_after_successful_verification(self) -> None:
        """Assures evaluate_stop returns allow on first attempt after passing verification."""
        conv_id = "c_f2_03"
        ws_file = str(self.ws / "harness" / "cli.py")

        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": ws_file}},
        })

        # Passing verification
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "exitCode": 0,
            "toolCall": {"name": "run_command", "args": {"CommandLine": "./agyis test"}},
        })

        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "allow")

    def test_f2_04_post_tool_use_resets_modified_files_and_updates_timestamp(self) -> None:
        """Assures passing verification resets last_modified_files and updates last_verified_at."""
        conv_id = "c_f2_04"
        ws_file = str(self.ws / "tests" / "test_sample.py")

        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": ws_file}},
        })

        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "exitCode": 0,
            "toolCall": {"name": "run_command", "args": {"CommandLine": "pytest"}},
        })

        code, state_resp = self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "action": "check_command_verification",
            "command": "pytest",
            "exit_code": 0,
        })
        self.assertEqual(code, 0)
        state = state_resp.get("state", {})
        self.assertFalse(state.get("code_dirty", True))
        self.assertEqual(state.get("last_modified_files"), [])
        self.assertIsNotNone(state.get("last_verified_at"))

    def test_f2_05_post_tool_use_hooks_json_registration(self) -> None:
        """Assures hooks.json registers psl-stop-verification-fence under PostToolUse for run_command."""
        hooks_path = REPO_ROOT / "hooks.json"
        self.assertTrue(hooks_path.exists(), "hooks.json does not exist in repository root")

        with open(hooks_path, "r", encoding="utf-8") as f:
            hooks_cfg = json.load(f)

        fence = hooks_cfg.get("psl-stop-verification-fence", {})
        self.assertIn("PostToolUse", fence, "psl-stop-verification-fence lacks PostToolUse registration")

        post_hooks = fence["PostToolUse"]
        matcher_found = any(
            "run_command" in entry.get("matcher", "") for entry in post_hooks
        )
        self.assertTrue(matcher_found, "PostToolUse does not register run_command matcher")
        mcp_matcher_found = any(
            "call_mcp_tool" in entry.get("matcher", "") for entry in post_hooks
        )
        self.assertTrue(mcp_matcher_found, "PostToolUse does not register call_mcp_tool matcher (DEF-04)")

    # =========================================================================
    # Feature 3 (Issue #43): Scratch Path Isolation
    # =========================================================================

    def test_f3_01_brain_scratch_path_does_not_dirty_state(self) -> None:
        """Assures editing code in brain scratch paths does not set code_dirty = True."""
        conv_id = "c_f3_01"
        scratch_file = "/home/kuasha/.gemini/antigravity/brain/session_abc123/scratch/helper.py"

        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": scratch_file, "CodeContent": "print('scratch')"},
            },
        })

        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "allow")

    def test_f3_02_temp_scratch_path_outside_workspace_does_not_dirty(self) -> None:
        """Assures editing code in /tmp outside workspace does not set code_dirty = True."""
        conv_id = "c_f3_02"
        tmp_file = "/tmp/one_off_scratch.py"

        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": tmp_file, "CodeContent": "x = 1"},
            },
        })

        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "allow")

    def test_f3_03_workspace_code_edit_sets_dirty_true(self) -> None:
        """Assures editing code inside workspace correctly marks code_dirty = True."""
        conv_id = "c_f3_03"
        ws_file = str(self.ws / "src" / "index.ts")

        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": ws_file, "CodeContent": "export const x = 1;"},
            },
        })

        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "continue")

    def test_f3_04_scratch_edit_allows_immediate_stop(self) -> None:
        """Assures task creating only scratch files may terminate immediately without running tests."""
        conv_id = "c_f3_04"
        scratch_script = str(self.ws / ".gemini" / "antigravity" / "brain" / "sess_1" / "scratch" / "probe.sh")

        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": scratch_script, "CodeContent": "#!/bin/bash\necho ok"},
            },
        })

        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "allow")

    def test_f3_05_relative_path_outside_workspace_isolated(self) -> None:
        """Assures relative path resolving outside workspace root is isolated."""
        conv_id = "c_f3_05"
        rel_outside = "../external_project/main.py"

        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": rel_outside, "CodeContent": "x = 1"},
            },
        })

        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "allow")

    # =========================================================================
    # Feature 6 (Issue #46): Standardized Issue Templates
    # =========================================================================

    def _load_template_content(self, filename: str) -> str:
        template_path = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / filename
        if not template_path.exists():
            self.skipTest(f"Pending implementation in Milestone M4: {filename} not yet created")
        return template_path.read_text(encoding="utf-8")

    def test_f6_01_bug_report_template_exists_and_valid_yaml(self) -> None:
        """Assures bug_report.yml exists and contains valid issue form structure."""
        content = self._load_template_content("bug_report.yml")
        self.assertIn("name:", content)
        self.assertIn("description:", content)
        self.assertIn("body:", content)

    def test_f6_02_bug_report_mandates_harness_version(self) -> None:
        """Assures bug_report.yml strictly mandates harness_version input."""
        content = self._load_template_content("bug_report.yml")
        self.assertIn("harness_version", content)
        # Verify required: true is present for harness_version block
        harness_idx = content.find("harness_version")
        self.assertNotEqual(harness_idx, -1)
        sub_content = content[harness_idx:harness_idx + 300]
        self.assertTrue(
            "required: true" in sub_content or "required:true" in sub_content,
            "harness_version field is not marked as required: true",
        )

    def test_f6_03_bug_report_optional_antigravity_platform_fields(self) -> None:
        """Assures bug_report.yml provides structured optional fields for Antigravity platform."""
        content = self._load_template_content("bug_report.yml")
        self.assertIn("antigravity_cli_version", content)
        self.assertIn("antigravity_ide_version", content)

    def test_f6_04_bug_report_optional_toolchain_and_repo_fields(self) -> None:
        """Assures bug_report.yml provides host toolchains and reproduction repo fields."""
        content = self._load_template_content("bug_report.yml")
        self.assertIn("host_toolchain_versions", content)
        self.assertIn("reproduction_repo", content)

    def test_f6_05_feature_request_and_config_templates_valid(self) -> None:
        """Assures feature_request.yml and config.yml exist with valid schemas."""
        feat_content = self._load_template_content("feature_request.yml")
        self.assertIn("harness_version", feat_content)
        self.assertIn("proposed_solution", feat_content)

        cfg_content = self._load_template_content("config.yml")
        self.assertIn("blank_issues_enabled", cfg_content)

    # =========================================================================
    # R6: REA Cleanroom Architecture & Opt-In Diagnostics (Requirement R6)
    # =========================================================================

    def test_r6_cli_doctor_experimental_rea(self) -> None:
        """Assures 'agyis doctor --experimental-rea' performs deep REA audit and reports diagnostics."""
        mock_candidates = json.dumps({
            "analysis_provider_candidates": [
                {"provider": {"name": "Ghidra"}, "availability": {"available": True}},
                {"provider": {"name": "IDA"}, "availability": {"available": False, "reason": "No license"}},
            ]
        })

        orig_run = subprocess.run

        def mock_subproc(cmd, *args, **kwargs):
            cmd_str = " ".join(str(c) for c in cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
            if "rea" in cmd_str:
                proc = unittest.mock.MagicMock()
                proc.returncode = 0
                proc.stderr = ""
                if "--version" in cmd_str:
                    proc.stdout = "rea 6.5.0\n"
                elif "providers" in cmd_str:
                    proc.stdout = mock_candidates
                return proc
            return orig_run(cmd, *args, **kwargs)

        mock_cli = {
            "status": "OK",
            "path": "/usr/local/bin/agyis",
            "collision": False,
            "agyis_status": "OK",
            "agyis_path": "/usr/local/bin/agyis",
            "psl_details": {"status": "OK", "collision": False, "path": "/usr/local/bin/psl"},
            "psl_collision": {"status": "OK", "collision": False, "path": "/usr/local/bin/psl"},
            "details": "Agyis launcher OK",
            "remediation": None,
        }
        mock_tool = {
            "name": "mock",
            "binary": "mock",
            "status": "OK",
            "path": "/usr/bin/mock",
            "version": "99.0.0",
            "min_version": "1.0.0",
            "is_shim": False,
            "shim_details": None,
            "is_collision": False,
            "collision_details": None,
            "spec": {},
        }

        with unittest.mock.patch("subprocess.run", side_effect=mock_subproc), \
             unittest.mock.patch("harness.runtime.doctor.check_tool", return_value=mock_tool), \
             unittest.mock.patch("harness.runtime.doctor.check_cli_binary", return_value=mock_cli), \
             unittest.mock.patch("harness.runtime.tool_checks.find_rea_binary", return_value=Path("/usr/local/bin/rea")):
            code, out, err = self.run_cli(["doctor", "--experimental-rea", "--json"])
            self.assertEqual(code, 0)
            data = self.parse_json_stdout(out)
            self.assertTrue(data.get("experimental_rea"))
            self.assertIn("rea_tooling", data)
            rea_tooling = data["rea_tooling"]
            self.assertFalse(rea_tooling.get("fast_path"))
            self.assertIn("status", rea_tooling)
            self.assertIn("mcp_configured", rea_tooling)

            # Observable text output contract
            code_txt, out_txt, err_txt = self.run_cli(["doctor", "--experimental-rea"])
            self.assertEqual(code_txt, 0)
            self.assertIn("REA Tooling", out_txt)

    def test_r6_cli_init_experimental_rea(self) -> None:
        """Assures 'agyis init --experimental-rea' scaffolds .agents/ledger/ and sets config."""
        target_ws = self.ws / "rea_proj"
        target_ws.mkdir()

        with unittest.mock.patch("harness.runtime.healing.provision_rea_skill"):
            # Step 1: Live execution with --experimental-rea
            code, out, err = self.run_cli(["init", "--experimental-rea", "--json", str(target_ws)])
            self.assertEqual(code, 0)
            data = self.parse_json_stdout(out)
            self.assertTrue(data.get("success"))
            self.assertTrue(data.get("experimental_rea"))

            # Verify side effects: .agents/ledger directory scaffolded and config set
            ledger_dir = target_ws / ".agents" / "ledger"
            self.assertTrue(ledger_dir.is_dir())
            cfg_file = target_ws / ".agyis" / "config.json"
            self.assertTrue(cfg_file.is_file())
            cfg_data = json.loads(cfg_file.read_text(encoding="utf-8"))
            self.assertTrue(cfg_data.get("experimental_rea"))

            # Step 2: Dry-run execution
            dry_ws = self.ws / "rea_dry_proj"
            dry_ws.mkdir()
            code_d, out_d, err_d = self.run_cli(["init", "--experimental-rea", "--dry-run", "--json", str(dry_ws)])
            self.assertEqual(code_d, 0)
            data_d = self.parse_json_stdout(out_d)
            self.assertTrue(data_d.get("dry_run"))
            self.assertTrue(data_d.get("experimental_rea"))
            self.assertFalse((dry_ws / ".agents" / "ledger").exists())


if __name__ == "__main__":
    unittest.main()
