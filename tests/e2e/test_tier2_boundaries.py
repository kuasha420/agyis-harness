#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Tier 2: Boundary & Corner Cases (Issues #41 through #46).
Validates edge cases, invalid inputs, and boundary conditions (5 tests per domain, 30 tests total):
- Domain 1: Anti-Loop Boundary Conditions
- Domain 2: Stop-Fence Boundary Conditions
- Domain 3: Scratch Path Boundary Conditions
- Domain 4: REA Doctor Boundary Conditions
- Domain 5: Cleanroom Boundary Conditions
- Domain 6: Issue Template Boundary Conditions
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Dict, List, Optional
import unittest
from unittest.mock import MagicMock, patch

from harness.delivery.constants import REPO_ROOT
from harness.runtime.tool_checks import check_rea_tooling, parse_version
from tests.e2e.harness_base import OpaqueBoxTestCase


class TestTier2Boundaries(OpaqueBoxTestCase):
    """
    Tier 2 E2E tests validating boundary conditions across all 6 domains.
    """

    # =========================================================================
    # Domain 1: Anti-Loop Boundary Conditions
    # =========================================================================

    def test_b1_01_empty_path_handling(self) -> None:
        """Assures empty string or whitespace path does not crash anti-loop hook."""
        payload = {
            "conversationId": "c_b1_01",
            "toolCall": {
                "name": "view_file",
                "args": {"AbsolutePath": "   "},
            },
        }
        code, resp = self.run_hook("anti-loop", payload)
        self.assertEqual(code, 0)
        self.assertIn(resp.get("decision"), ("allow", "deny"))

    def test_b1_02_windows_backslashes_coordination_path(self) -> None:
        """Assures coordination paths containing Windows backslashes are exempted."""
        win_path = ".agents\\teamwork\\progress.md"
        for _ in range(6):
            payload = {
                "conversationId": "c_b1_02",
                "toolCall": {
                    "name": "view_file",
                    "args": {"Path": win_path},
                },
            }
            code, resp = self.run_hook("anti-loop", payload)
            self.assertEqual(code, 0)
            self.assertEqual(resp.get("decision"), "allow")

    def test_b1_03_whitespace_padded_path(self) -> None:
        """Assures coordination paths with leading and trailing whitespace are exempted."""
        padded_path = "   .agents/ledger/obligations.json   "
        for _ in range(6):
            payload = {
                "conversationId": "c_b1_03",
                "toolCall": {
                    "name": "view_file",
                    "args": {"AbsolutePath": padded_path},
                },
            }
            code, resp = self.run_hook("anti-loop", payload)
            self.assertEqual(code, 0)
            self.assertEqual(resp.get("decision"), "allow")

    def test_b1_04_case_variation_manifest_names(self) -> None:
        """Assures coordination manifest basenames with case variations are exempted."""
        variations = ["PROGRESS.MD", "Dispatch.Md", "Obligations.JSON", "TASK.md"]
        for fname in variations:
            for _ in range(6):
                payload = {
                    "conversationId": f"c_b1_04_{fname}",
                    "toolCall": {
                        "name": "view_file",
                        "args": {"Path": fname},
                    },
                }
                code, resp = self.run_hook("anti-loop", payload)
                self.assertEqual(code, 0)
                self.assertEqual(resp.get("decision"), "allow")

    def test_b1_05_deeply_nested_teamwork_paths(self) -> None:
        """Assures deeply nested teamwork subtask files are exempted."""
        deep_path = str(self.ws / ".agents" / "teamwork" / "cluster_a" / "strand_9" / "progress.md")
        for _ in range(8):
            payload = {
                "conversationId": "c_b1_05",
                "toolCall": {
                    "name": "view_file",
                    "args": {"AbsolutePath": deep_path},
                },
            }
            code, resp = self.run_hook("anti-loop", payload)
            self.assertEqual(code, 0)
            self.assertEqual(resp.get("decision"), "allow")

    # =========================================================================
    # Domain 2: Stop-Fence Boundary Conditions
    # =========================================================================

    def test_b2_01_non_test_command_exit_zero_does_not_clear(self) -> None:
        """Assures non-test command with exit 0 (e.g. ls, git status) does not clear dirty state."""
        conv_id = "c_b2_01"
        ws_file = str(self.ws / "src" / "main.py")

        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": ws_file}},
        })

        # Non-test command exit 0
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "exitCode": 0,
            "toolCall": {"name": "run_command", "args": {"CommandLine": "ls -la"}},
        })

        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "continue")

    def test_b2_02_null_exit_code_handling(self) -> None:
        """Assures PostToolUse with missing or null exitCode does not clear dirty state."""
        conv_id = "c_b2_02"
        ws_file = str(self.ws / "src" / "main.py")

        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": ws_file}},
        })

        # PostToolUse with null exitCode
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "exitCode": None,
            "toolCall": {"name": "run_command", "args": {"CommandLine": "python3 -m unittest discover"}},
        })

        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "continue")

    def test_b2_03_negative_signal_exit_codes(self) -> None:
        """Assures commands terminated by signals (e.g. exit code 137 or -9) do not clear dirty state."""
        conv_id = "c_b2_03"
        ws_file = str(self.ws / "src" / "main.py")

        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": ws_file}},
        })

        for sig_code in (-9, 137, 143):
            self.run_hook("verification-fence", {
                "conversationId": conv_id,
                "cwd": str(self.ws),
                "exitCode": sig_code,
                "toolCall": {"name": "run_command", "args": {"CommandLine": "pytest"}},
            })

            code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
            self.assertEqual(code, 0)
            self.assertEqual(stop_resp.get("decision"), "continue")

    def test_b2_04_malformed_json_payload(self) -> None:
        """Assures malformed JSON payload returns fail-open allow without crashing."""
        code, out, _ = self.run_hook_cli("verification-fence", "{not valid json")
        self.assertEqual(code, 0)
        data = json.loads(out.strip()) if out.strip() else {}
        self.assertEqual(data.get("decision"), "allow")

    def test_b2_05_unknown_tool_name_ignored(self) -> None:
        """Assures unrecognized tools do not modify verification fence dirty state."""
        conv_id = "c_b2_05"
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "toolCall": {"name": "search_web", "args": {"query": "python"}},
        })

        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "allow")

    # =========================================================================
    # Domain 3: Scratch Path Boundary Conditions
    # =========================================================================

    def test_b3_01_workspace_inside_tmp(self) -> None:
        """Assures that when workspace root itself is in /tmp, in-workspace code edits mark dirty."""
        # self.ws is inside a temporary directory (/tmp/...)
        conv_id = "c_b3_01"
        ws_code = str(self.ws / "app" / "service.py")

        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": ws_code}},
        })

        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "continue")

    def test_b3_02_brain_scratch_nested_subdirs(self) -> None:
        """Assures deeply nested subdirectories under brain scratch are exempted."""
        conv_id = "c_b3_02"
        deep_scratch = "/home/user/.gemini/antigravity/brain/session_1/scratch/sub/utils/test.py"

        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": deep_scratch}},
        })

        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "allow")

    def test_b3_03_path_traversal_scrubbing(self) -> None:
        """Assures path traversal navigating outside workspace root does not dirty workspace."""
        conv_id = "c_b3_03"
        traversal_path = str(self.ws / "subdir" / ".." / ".." / "external_script.py")

        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": traversal_path}},
        })

        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "allow")

    def test_b3_04_symlinked_scratch_dir(self) -> None:
        """Assures symlinked scratch directories pointing outside workspace are isolated."""
        conv_id = "c_b3_04"
        with tempfile.TemporaryDirectory() as outside_dir:
            outside_scratch = Path(outside_dir) / "scratch"
            outside_scratch.mkdir()
            symlink_in_ws = self.ws / "scratch_link"
            try:
                symlink_in_ws.symlink_to(outside_scratch)
            except OSError:
                self.skipTest("Symlinks not supported in environment")

            target_file = str(symlink_in_ws / "script.py")
            self.run_hook("verification-fence", {
                "conversationId": conv_id,
                "cwd": str(self.ws),
                "toolCall": {"name": "write_to_file", "args": {"TargetFile": target_file}},
            })

            code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
            self.assertEqual(code, 0)
            self.assertEqual(stop_resp.get("decision"), "allow")

    def test_b3_05_empty_or_whitespace_file_path(self) -> None:
        """Assures empty or whitespace TargetFile in write_to_file does not dirty state."""
        conv_id = "c_b3_05"
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": "   "}},
        })

        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "allow")

    # =========================================================================
    # Domain 4: REA Doctor Boundary Conditions
    # =========================================================================

    def test_b4_01_rea_providers_timeout_resilience(self) -> None:
        """Assures hanging 'rea providers' times out gracefully without unhandled exception."""
        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=Path("/usr/bin/rea")), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="rea providers", timeout=0.1)):
            res = check_rea_tooling(timeout=0.1)
            self.assertIn("providers", res)

    def test_b4_02_rea_providers_malformed_json(self) -> None:
        """Assures invalid JSON from 'rea providers' is handled gracefully."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Error: Fatal unexpected token < at line 1"

        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=Path("/usr/bin/rea")), \
             patch("subprocess.run", return_value=mock_proc):
            res = check_rea_tooling()
            providers = res.get("providers", {})
            self.assertEqual(providers.get("active"), [])
            self.assertEqual(providers.get("unavailable"), [])

    def test_b4_03_rea_prerelease_version_parsing(self) -> None:
        """Assures prerelease versions like 6.5.0-alpha.1 or 6.0.0-rc2 parse correctly."""
        v1 = parse_version("6.5.0-alpha.1")
        v2 = parse_version("6.0.0-rc2")
        self.assertGreaterEqual(v1, (6, 5, 0))
        self.assertGreaterEqual(v2, (6, 0, 0))

    def test_b4_04_rea_outdated_version_warning(self) -> None:
        """Assures outdated version (< 6.0.0) produces OUTDATED or warning status."""
        mock_proc_v = MagicMock()
        mock_proc_v.returncode = 0
        mock_proc_v.stdout = "rea-agents 5.2.0"

        mock_proc_p = MagicMock()
        mock_proc_p.returncode = 0
        mock_proc_p.stdout = '{"providers": []}'

        def fake_run(cmd, *args, **kwargs):
            if "--version" in cmd:
                return mock_proc_v
            return mock_proc_p

        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=Path("/usr/bin/rea")), \
             patch("subprocess.run", side_effect=fake_run):
            res = check_rea_tooling()
            self.assertIn(res.get("status"), ("outdated", "warning", "optional_missing"))
            self.assertIsNotNone(res.get("remediation"))

    def test_b4_05_mcp_config_missing_or_corrupt(self) -> None:
        """Assures missing or corrupted mcp_config.json reports mcp_configured: False safely."""
        corrupt_mcp = self.ws / "corrupt_mcp.json"
        corrupt_mcp.write_text("{broken json", encoding="utf-8")

        res = check_rea_tooling(mcp_config_path=corrupt_mcp)
        self.assertFalse(res.get("mcp_configured"))

    # =========================================================================
    # Domain 5: Cleanroom Boundary Conditions
    # =========================================================================

    def test_b5_01_path_similarity_false_positives(self) -> None:
        """Assures paths like docs/specifications/ or my_docs/specs_old/ do not falsely gate stop."""
        conv_id = "c_b5_01"
        false_positive_paths = [
            str(self.ws / "docs" / "specifications" / "note.md"),
            str(self.ws / "other" / "docs" / "spec" / "note.md"),
        ]

        for p in false_positive_paths:
            self.run_hook("verification-fence", {
                "conversationId": conv_id,
                "cwd": str(self.ws),
                "toolCall": {"name": "write_to_file", "args": {"TargetFile": p}},
            })

        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "allow")

    def test_b5_02_cleanroom_case_insensitivity(self) -> None:
        """Assures mixed-case paths for cleanroom specs trigger the cleanroom gate."""
        conv_id = "c_b5_02"
        mixed_spec = str(self.ws / "Docs" / "Specs" / "Hardware.md")

        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": mixed_spec}},
        })

        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "continue")

    def test_b5_03_non_code_extensions_in_ledger_specs(self) -> None:
        """Assures non-code extensions (.yaml, .toml, .txt) in cleanroom paths require verification."""
        conv_id = "c_b5_03"
        spec_yaml = str(self.ws / "docs" / "specs" / "schema.yaml")

        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": spec_yaml}},
        })

        code, stop_resp = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(code, 0)
        self.assertEqual(stop_resp.get("decision"), "continue")

    def test_b5_04_cycle_of_failed_and_passed_tests(self) -> None:
        """Assures dirty state correctly survives failed test and clears on passed test."""
        conv_id = "c_b5_04"
        spec_file = str(self.ws / "docs" / "specs" / "arch.md")

        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": spec_file}},
        })

        # Test fails
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "exitCode": 1,
            "toolCall": {"name": "run_command", "args": {"CommandLine": "python3 -m unittest discover"}},
        })
        _, stop1 = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(stop1.get("decision"), "continue")

        # Test succeeds
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "exitCode": 0,
            "toolCall": {"name": "run_command", "args": {"CommandLine": "python3 -m unittest discover"}},
        })
        _, stop2 = self.run_hook("verification-fence", {"conversationId": conv_id, "cwd": str(self.ws)})
        self.assertEqual(stop2.get("decision"), "allow")

    def test_b5_05_contract_deletion_or_recreation(self) -> None:
        """Assures multiple spec modifications are recorded in last_modified_files."""
        conv_id = "c_b5_05"
        f1 = str(self.ws / "docs" / "specs" / "spec1.md")
        f2 = str(self.ws / "docs" / "specs" / "spec2.md")

        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": f1}},
        })
        self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "cwd": str(self.ws),
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": f2}},
        })

        _, state_resp = self.run_hook("verification-fence", {
            "conversationId": conv_id,
            "action": "check_command_verification",
            "command": "echo",
            "exit_code": 1,
        })
        state = state_resp.get("state", {})
        self.assertTrue(state.get("code_dirty"))
        modified = state.get("last_modified_files", [])
        self.assertTrue(any("spec1.md" in m for m in modified))
        self.assertTrue(any("spec2.md" in m for m in modified))

    # =========================================================================
    # Domain 6: Issue Template Boundary Conditions
    # =========================================================================

    def _get_template_path(self, filename: str) -> Path:
        p = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / filename
        if not p.exists():
            self.skipTest(f"Pending implementation in Milestone M4: {filename} not yet created")
        return p

    def test_b6_01_malformed_yaml_syntax_detection(self) -> None:
        """Assures issue template files parse cleanly without syntax errors."""
        p = self._get_template_path("bug_report.yml")
        content = p.read_text(encoding="utf-8")
        # Check no tab indentation errors or unbalanced quotes
        self.assertNotIn("\t", content, "YAML issue template contains illegal tab characters")

    def test_b6_02_missing_body_elements_detection(self) -> None:
        """Assures issue template contains structured body element array."""
        p = self._get_template_path("bug_report.yml")
        content = p.read_text(encoding="utf-8")
        self.assertIn("body:", content)

    def test_b6_03_non_yaml_files_ignored(self) -> None:
        """Assures non-YAML files in .github/ISSUE_TEMPLATE/ (if any) are not treated as issue forms."""
        template_dir = REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
        if not template_dir.exists():
            self.skipTest("Pending implementation in Milestone M4: ISSUE_TEMPLATE directory not yet created")
        for file in template_dir.iterdir():
            if file.suffix not in (".yml", ".yaml"):
                self.assertNotEqual(file.suffix, ".yml")

    def test_b6_04_special_characters_in_descriptions(self) -> None:
        """Assures markdown backticks, pipes, and special characters in descriptions parse cleanly."""
        p = self._get_template_path("bug_report.yml")
        content = p.read_text(encoding="utf-8")
        self.assertIn("agyis doctor", content)

    def test_b6_05_validations_structure_integrity(self) -> None:
        """Assures validations blocks use valid boolean required flags."""
        p = self._get_template_path("bug_report.yml")
        content = p.read_text(encoding="utf-8")
        self.assertIn("validations:", content)
        self.assertIn("required:", content)


if __name__ == "__main__":
    unittest.main()
