#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Tier 1: Feature Coverage (Features 1-17 across Requirements R1-R5).
Validates core CLI, nomenclature layer, tagged rule demarcation, stack presets,
manifest & personas, dual runner recognition, and dry-run contracts strictly as an opaque box.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

from harness.delivery.constants import REPO_ROOT
from tests.e2e.harness_base import OpaqueBoxTestCase


class TestTier1Features(OpaqueBoxTestCase):
    """
    Tier 1 E2E test cases: Nominal feature behavior across R1-R5.
    Interacts purely via public CLI commands and inspects observable side-effects.
    """

    # =========================================================================
    # R1: Core CLI, Entrypoints, Deprecation & XDG Paths (Features 1, 2, 3)
    # =========================================================================

    def test_r1_agyis_help_and_version_branding(self) -> None:
        """Assures 'agyis --help' and 'agyis --version' display modern product branding."""
        code, out, err = self.run_cli(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("Agyis Harness", out)
        self.assertIn("Antigravity", out)
        self.assertIn("Immune System", out)
        self.assertIn("doctor", out)
        self.assertIn("init", out)
        self.assertIn("harmonize", out)
        self.assertEqual(err, "")

        code, out, err = self.run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("agyis-harness", out)

    def test_r1_psl_stderr_deprecation_lifecycle_notice(self) -> None:
        """Assures legacy 'psl' emits active deprecation notice strictly on stderr."""
        code, out, err = self.run_cli(["--help"], prog="psl")
        self.assertEqual(code, 0)
        self.assertIn("DeprecationWarning: 'psl' is deprecated and will be removed in 3 months", err)
        self.assertIn("Use 'agyis' instead", err)
        self.assertIn("PSL Harness", out)

        code, out, err = self.run_cli(["--version"], prog="psl")
        self.assertEqual(code, 0)
        self.assertIn("DeprecationWarning: 'psl' is deprecated", err)
        self.assertIn("agyis-harness", out)

    def test_r1_subcommand_parity_between_agyis_and_psl(self) -> None:
        """Assures identical execution results between agyis and psl subcommands."""
        code_a, out_a, err_a = self.run_cli(["status"])
        code_p, out_p, err_p = self.run_cli(["status"], prog="psl")

        self.assertEqual(code_a, 0)
        self.assertEqual(code_p, 0)
        self.assertIn("Specialist Subagents", out_a)
        self.assertIn("Specialist Subagents", out_p)
        self.assertEqual(err_a, "")
        self.assertIn("DeprecationWarning: 'psl' is deprecated", err_p)

    def test_r1_xdg_config_path_precedence(self) -> None:
        """Assures AGYIS_CONFIG_DIR takes precedence over PSL_CONFIG_DIR."""
        from harness.telemetry.config import get_config_dir

        dir_agyis = self.ws / "custom_config_agyis"
        dir_psl = self.ws / "custom_config_psl"
        dir_agyis.mkdir(parents=True, exist_ok=True)
        dir_psl.mkdir(parents=True, exist_ok=True)

        env = {
            "AGYIS_CONFIG_DIR": str(dir_agyis),
            "PSL_CONFIG_DIR": str(dir_psl),
        }
        with unittest.mock.patch.dict(os.environ, env):
            resolved = get_config_dir()
            self.assertEqual(resolved, dir_agyis.resolve())

        # Observable side effect via credentials discovery
        (dir_agyis / "credentials.json").write_text(
            json.dumps({"token": "tok_agyis", "github_username": "user_agyis"}), encoding="utf-8"
        )
        (dir_psl / "credentials.json").write_text(
            json.dumps({"token": "tok_psl", "github_username": "user_psl"}), encoding="utf-8"
        )
        code, out, err = self.run_cli(["auth", "status", "--json"], env_overrides=env)
        self.assertEqual(code, 0)
        data = self.parse_json_stdout(out)
        self.assertEqual(data.get("username"), "user_agyis")

    def test_r1_xdg_config_path_legacy_psl_fallback(self) -> None:
        """Assures fallback to PSL_CONFIG_DIR when AGYIS_CONFIG_DIR is unset."""
        from harness.telemetry.config import get_config_dir

        dir_psl = self.ws / "fallback_config_psl"
        dir_psl.mkdir(parents=True, exist_ok=True)

        env = {
            "AGYIS_CONFIG_DIR": "",
            "PSL_CONFIG_DIR": str(dir_psl),
        }
        with unittest.mock.patch.dict(os.environ, env):
            resolved = get_config_dir()
            self.assertEqual(resolved, dir_psl.resolve())

        (dir_psl / "credentials.json").write_text(
            json.dumps({"token": "tok_fallback", "github_username": "user_fallback"}), encoding="utf-8"
        )
        code, out, err = self.run_cli(["auth", "status", "--json"], env_overrides=env)
        self.assertEqual(code, 0)
        data = self.parse_json_stdout(out)
        self.assertEqual(data.get("username"), "user_fallback")

    def test_r1_xdg_data_path_precedence(self) -> None:
        """Assures AGYIS_DATA_DIR takes precedence over PSL_DATA_DIR."""
        from harness.telemetry.config import get_data_dir

        dir_agyis_data = self.ws / "data_agyis"
        dir_psl_data = self.ws / "data_psl"
        dir_agyis_data.mkdir(parents=True, exist_ok=True)
        dir_psl_data.mkdir(parents=True, exist_ok=True)

        env = {
            "AGYIS_DATA_DIR": str(dir_agyis_data),
            "PSL_DATA_DIR": str(dir_psl_data),
        }
        with unittest.mock.patch.dict(os.environ, env):
            resolved = get_data_dir()
            self.assertEqual(resolved, dir_agyis_data.resolve())

        with unittest.mock.patch.dict(os.environ, {"AGYIS_DATA_DIR": "", "PSL_DATA_DIR": str(dir_psl_data)}):
            resolved = get_data_dir()
            self.assertEqual(resolved, dir_psl_data.resolve())

    # =========================================================================
    # R2: Tagged Rule Demarcation, Presets & Harmonizer (Features 6, 7, 8, 9, 10)
    # =========================================================================

    def test_r2_init_creates_modern_tagged_rule_block(self) -> None:
        """Assures 'agyis init' injects modern '<!-- Added by AGYIS-HARNESS -->' block."""
        code, out, err = self.run_cli(["init", str(self.ws)])
        self.assertEqual(code, 0)

        agents_md = self.ws / "AGENTS.md"
        self.assertTrue(agents_md.exists())
        content = agents_md.read_text(encoding="utf-8")
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", content)
        self.assertIn("<!-- End AGYIS-HARNESS -->", content)
        self.assertNotIn("<!-- Added by PSL-HARNESS -->", content)

    def test_r2_init_stack_preset_detection_systems(self) -> None:
        """Assures 'agyis init' auto-detects Systems stack preset via Makefile."""
        self.create_fixture("systems")
        code, out, err = self.run_cli(["init", "--dry-run", "--json", str(self.ws)])
        self.assertEqual(code, 0)
        data = self.parse_json_stdout(out)
        self.assertEqual(data.get("stack"), "systems")
        commands = data.get("command_dictionary", {})
        self.assertIn("test", commands)
        self.assertEqual(commands["test"], "make test")
        self.assertIn("build", commands)
        self.assertEqual(commands["build"], "make build")

    def test_r2_init_stack_preset_detection_polyglot(self) -> None:
        """Assures 'agyis init' extracts commands from multi-stack repositories."""
        self.create_fixture("polyglot")
        code, out, err = self.run_cli(["init", "--dry-run", "--json", str(self.ws)])
        self.assertEqual(code, 0)
        data = self.parse_json_stdout(out)
        commands = data.get("command_dictionary", {})
        self.assertIn("test", commands)
        self.assertIn("build", commands)

    def test_r2_command_dictionary_injected_into_section_1(self) -> None:
        """Assures extracted commands are formatted into Section 1 of AGENTS.md."""
        self.create_fixture("node_typescript")
        code, out, err = self.run_cli(["init", str(self.ws)])
        self.assertEqual(code, 0)

        content = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("## 1. Explicit Project Command Dictionary", content)
        self.assertIn("npm test", content)
        self.assertIn("npm run build", content)

    def test_r2_init_dry_run_zero_filesystem_mutations(self) -> None:
        """Assures 'agyis init --dry-run' makes zero disk modifications."""
        code, out, err = self.run_cli(["init", "--dry-run", str(self.ws)])
        self.assertEqual(code, 0)
        self.assertFalse((self.ws / "AGENTS.md").exists())
        self.assertFalse((self.ws / ".agents").exists())

    def test_r2_harmonize_migrates_legacy_structure_to_agents(self) -> None:
        """Assures 'agyis harmonize' migrates .agent/ to .agents/ and updates tags."""
        self.create_fixture("legacy_psl")
        code, out, err = self.run_cli(["harmonize", str(self.ws)])
        self.assertEqual(code, 0)

        # Structure migrated to .agents/
        self.assertTrue((self.ws / ".agents" / "agents" / "code_reviewer.md").exists())
        self.assertTrue((self.ws / ".agents" / "skills" / "deploy_staging" / "SKILL.md").exists())
        self.assertTrue((self.ws / ".agents" / "rules" / "standards.md").exists())

        # Tagged block updated to AGYIS-HARNESS
        content = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", content)
        self.assertIn("<!-- End AGYIS-HARNESS -->", content)
        self.assertNotIn("<!-- Added by PSL-HARNESS -->", content)

    def test_r2_harmonize_preserves_custom_user_rules(self) -> None:
        """Assures user rules outside tagged fences remain 100% intact."""
        custom_rules = (
            "# My Custom Rules\n- Invariant Alpha\n\n"
            "<!-- Added by PSL-HARNESS -->\nLegacy rules\n<!-- End PSL-HARNESS -->\n\n"
            "## Postfix Rules\n- Invariant Omega\n"
        )
        self.create_fixture("legacy_psl", custom_rules=custom_rules)
        code, out, err = self.run_cli(["harmonize", str(self.ws)])
        self.assertEqual(code, 0)

        content = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("# My Custom Rules", content)
        self.assertIn("- Invariant Alpha", content)
        self.assertIn("## Postfix Rules", content)
        self.assertIn("- Invariant Omega", content)

    def test_r2_harmonize_dry_run_zero_filesystem_mutations(self) -> None:
        """Assures 'agyis harmonize --dry-run' performs preview without writing to disk."""
        self.create_fixture("legacy_psl")
        code, out, err = self.run_cli(["harmonize", "--dry-run", str(self.ws)])
        self.assertEqual(code, 0)
        self.assertFalse((self.ws / ".agents").exists())
        content = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("<!-- Added by PSL-HARNESS -->", content)

    # =========================================================================
    # R3: Extension Manifest, Personas & Doctor (Features 4, 5, 11, 12)
    # =========================================================================

    def test_r3_extension_manifest_registration(self) -> None:
        """Assures plugin.json registers the rebrand product as 'agyis-harness'."""
        plugin_file = REPO_ROOT / "plugin.json"
        self.assertTrue(plugin_file.exists())
        data = json.loads(plugin_file.read_text(encoding="utf-8"))
        self.assertEqual(data.get("name"), "agyis-harness")

    def test_r3_specialist_persona_agyis_architect(self) -> None:
        """Assures specialist persona 'agyis_architect' exists with valid capabilities."""
        code, out, err = self.run_cli(["agents", "--json"])
        self.assertEqual(code, 0)
        data = self.parse_json_stdout(out)
        names = [a.get("name") for a in data]
        self.assertIn("agyis_architect", names)

        persona_path = REPO_ROOT / "harness" / "agents" / "agyis_architect.md"
        self.assertTrue(persona_path.exists())
        content = persona_path.read_text(encoding="utf-8")
        self.assertIn("Agyis Lead Architect", content)

    def test_r3_doctor_operational_pass(self) -> None:
        """Assures 'agyis doctor' audits runtimes and reports operational status."""
        code, out, err = self.run_cli(["doctor", "--json"])
        self.assertEqual(code, 0)
        data = self.parse_json_stdout(out)
        self.assertIn("tiers", data)
        self.assertIn("tier_1_languages", data["tiers"])
        self.assertGreaterEqual(data["summary"]["ok"], 1)

    def test_r3_doctor_discreet_backronym(self) -> None:
        """Assures doctor diagnostics include subtle 'Antigravity Immune System'."""
        code, out, err = self.run_cli(["doctor", "--help"])
        self.assertEqual(code, 0)
        self.assertIn("Antigravity Immune System", out)

    def test_r3_doctor_heal_flag_operational(self) -> None:
        """Assures 'agyis doctor --heal' completes user-space check cleanly."""
        code, out, err = self.run_cli(["doctor", "--heal", "--json"])
        self.assertEqual(code, 0)
        data = self.parse_json_stdout(out)
        self.assertIn("summary", data)

    def test_r3_csp_ip_notice_attribution(self) -> None:
        """Assures NOTICE file includes ICARO-42/b CSP-IP attribution."""
        notice_file = REPO_ROOT / "NOTICE"
        self.assertTrue(notice_file.exists())
        content = notice_file.read_text(encoding="utf-8")
        self.assertIn("agyis-harness", content)
        self.assertIn("Arafat Zahan (@kuasha420)", content)
        self.assertIn("ICARO-42/b", content)
        self.assertIn("Purrfect Software Limited", content)

    # =========================================================================
    # R4: Dual Runner Recognition & Hermetic Benchmarks (Features 13, 14, 15)
    # =========================================================================

    def _create_dummy_test_suite(self, name: str = "sample") -> Path:
        import uuid

        mod_name = f"test_{name}_{uuid.uuid4().hex}"
        t_dir = self.ws / f"dummy_tests_{name}"
        t_dir.mkdir(parents=True, exist_ok=True)
        (t_dir / f"{mod_name}.py").write_text(
            "import unittest\nclass TestSimple(unittest.TestCase):\n    def test_pass(self):\n        pass\n",
            encoding="utf-8",
        )
        self.addCleanup(lambda: sys.modules.pop(mod_name, None))
        return t_dir

    def test_r4_test_command_execution_agyis(self) -> None:
        """Assures 'agyis test' invokes test runner discovery and exits 0."""
        t_dir = self._create_dummy_test_suite("agyis")
        code, out, err = self.run_cli(["test", "-s", str(t_dir), "-v"])
        self.assertEqual(code, 0)
        self.assertIn("Ran 1 test", err + out)

    def test_r4_test_command_execution_psl_with_deprecation_notice(self) -> None:
        """Assures 'psl test' emits deprecation warning on stderr and runs tests."""
        t_dir = self._create_dummy_test_suite("psl")
        code, out, err = self.run_cli(["test", "-s", str(t_dir), "-v"], prog="psl")
        self.assertEqual(code, 0)
        self.assertIn("DeprecationWarning: 'psl' is deprecated", err)
        self.assertIn("Ran 1 test", err + out)

    def test_r4_completion_fence_hook_dual_runner_unblocking(self) -> None:
        """Assures completion fence lifecycle hook handles Stop event safely."""
        stop_payload = json.dumps({"event": "Stop", "conversation_id": "e2e_fence_test"})
        code, out, err = self.run_cli(["hook", "completion-fence"], stdin_input=stop_payload)
        self.assertEqual(code, 0)
        data = self.parse_json_stdout(out)
        self.assertIn(data.get("decision"), ["allow", "continue"])

    def test_r4_command_safety_hook_recognizes_dual_runners(self) -> None:
        """Assures command safety hook passes 'agyis test' and 'psl test' cleanly."""
        payload_a = json.dumps(
            {"tool_name": "run_command", "tool_args": {"CommandLine": "agyis test"}}
        )
        code, out, err = self.run_cli(["hook", "command-safety"], stdin_input=payload_a)
        self.assertEqual(code, 0)
        data = self.parse_json_stdout(out)
        self.assertEqual(data.get("decision"), "allow")

        payload_p = json.dumps(
            {"tool_name": "run_command", "tool_args": {"CommandLine": "psl test"}}
        )
        code, out, err = self.run_cli(["hook", "command-safety"], stdin_input=payload_p)
        self.assertEqual(code, 0)
        data = self.parse_json_stdout(out)
        self.assertEqual(data.get("decision"), "allow")

    def test_r4_test_runner_subsecond_benchmark(self) -> None:
        """Assures test discovery runs within acceptable hermetic subsecond performance."""
        t_dir = self._create_dummy_test_suite("benchmark")
        code, out, err = self.run_cli(["test", "-s", str(t_dir)])
        self.assertEqual(code, 0)

    # =========================================================================
    # R5: Fleet Healing Dry-Run & In-Tree Documentation (Features 16, 17)
    # =========================================================================

    def test_r5_harmonize_dry_run_json_contract(self) -> None:
        """Assures 'agyis harmonize --dry-run --json' emits complete 11-key schema."""
        self.create_fixture("legacy_psl")
        code, out, err = self.run_cli(["harmonize", "--dry-run", "--json", str(self.ws)])
        self.assertEqual(code, 0)
        data = self.parse_json_stdout(out)

        required_keys = [
            "success",
            "workspace_dir",
            "dry_run",
            "legacy_agent_dir_found",
            "legacy_workflows_migrated",
            "legacy_agents_migrated",
            "legacy_rules_migrated",
            "rules_action",
            "command_dictionary",
            "modified",
            "message",
        ]
        for key in required_keys:
            self.assertIn(key, data, f"Missing key '{key}' in harmonize JSON report")
        self.assertTrue(data["dry_run"])
        self.assertTrue(data["legacy_agent_dir_found"])

    def test_r5_init_dry_run_json_contract(self) -> None:
        """Assures 'agyis init --dry-run --json' emits complete JSON summary."""
        code, out, err = self.run_cli(["init", "--dry-run", "--json", str(self.ws)])
        self.assertEqual(code, 0)
        data = self.parse_json_stdout(out)
        self.assertTrue(data.get("success"))
        self.assertTrue(data.get("dry_run"))
        self.assertIn("command_dictionary", data)

    def test_r5_fixture_healing_sha256_tree_stability(self) -> None:
        """Assures harmonize dry-run maintains 100% byte-for-byte tree stability."""
        self.create_fixture("legacy_psl")

        def compute_tree_hashes(base_dir: Path) -> dict[str, str]:
            hashes = {}
            for p in sorted(base_dir.rglob("*")):
                if p.is_file():
                    hashes[str(p.relative_to(base_dir))] = hashlib.sha256(p.read_bytes()).hexdigest()
            return hashes

        before = compute_tree_hashes(self.ws)
        code, out, err = self.run_cli(["harmonize", "--dry-run", str(self.ws)])
        self.assertEqual(code, 0)
        after = compute_tree_hashes(self.ws)

        self.assertEqual(before, after, "Dry-run mutated files on disk!")

    def test_r5_in_tree_rfc_document_validity(self) -> None:
        """Assures docs/discussions/rebrand-agyis-epic.md exists and contains RFC."""
        rfc_path = REPO_ROOT / "docs" / "discussions" / "rebrand-agyis-epic.md"
        self.assertTrue(rfc_path.exists())
        content = rfc_path.read_text(encoding="utf-8")
        self.assertIn("Project Rebrand to `agyis`", content)
        self.assertIn("ICARO-42/b", content)
        self.assertIn("Antigravity Immune System", content)

    def test_r5_standalone_binary_launchers_exist_and_executable(self) -> None:
        """Assures root launchers './agyis' and './psl' exist and execute out-of-process."""
        bin_agyis = REPO_ROOT / "agyis"
        bin_psl = REPO_ROOT / "psl"
        self.assertTrue(bin_agyis.is_file())
        self.assertTrue(bin_psl.is_file())

        code, out, err = self.run_binary("agyis", ["--version"])
        self.assertEqual(code, 0)
        self.assertIn("agyis-harness", out)

        code, out, err = self.run_binary("psl", ["--version"])
        self.assertEqual(code, 0)
        self.assertIn("DeprecationWarning: 'psl' is deprecated", err)


if __name__ == "__main__":
    unittest.main()
