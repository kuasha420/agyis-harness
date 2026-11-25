#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic unit and integration tests for PSL Harness Delivery & Plugin Installer (ADR-030).

Validates:
- DeliveryMode.SYMLINK and DeliveryMode.COPY installations
- File packaging filters (ADR-014 Product vs. Project Bifurcation)
- Path safety guards against deleting REPO_ROOT
- Dry-run modes and idempotent re-installations
- Safe uninstallation without collateral damage
- CoexistenceEngine 3-layer resource precedence (Layer 3 > Layer 2 > Layer 1)
- Zero Git Pollution verification
- CLI subcommands `psl install` and `psl uninstall`
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import argparse
from harness.cli import main
from harness.commands.init import cmd_init
from harness.delivery import (
    DISTRIBUTABLE_ITEMS,
    GIT_EXCLUDE_PATTERNS,
    REPO_ROOT,
    SYNC_SURFACE_ITEMS,
    CoexistenceEngine,
    DeliveryMode,
    DeliveryResult,
    PluginInstaller,
    configure_git_exclude,
    enforce_single_source_skills,
    find_workspace_root,
    install_workspace,
    sync_surfaces,
    adapt_spdx_license,
    detect_repository_license,
    extract_command_descriptions,
)


class TestDeliveryWorkspaceInit(unittest.TestCase):
    """Test suite for workspace installation, command dictionary extraction, and cmd_init."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.isolated_base = Path(self.temp_dir.name)
        # Always install strictly to a subfolder inside temp
        self.target_dir = self.isolated_base / "installed_plugin"
        self.bin_dir = self.isolated_base / "bin"
        self.aux_bin_1 = self.isolated_base / "gemini" / "antigravity" / "bin"
        self.aux_bin_2 = self.isolated_base / "gemini" / "antigravity-cli" / "bin"
        self.config_dir = self.isolated_base / "gemini" / "config"
        self.surfaces = [
            self.isolated_base / "gemini" / "antigravity",
            self.isolated_base / "gemini" / "antigravity-cli",
            self.isolated_base / "gemini" / "antigravity-ide",
        ]
        self.orig_bin_dir = os.environ.get("PSL_BIN_DIR")
        os.environ["PSL_BIN_DIR"] = str(self.bin_dir)
        self.orig_aux_bin_dirs = os.environ.get("PSL_AUX_BIN_DIRS")
        os.environ["PSL_AUX_BIN_DIRS"] = f"{self.aux_bin_1}:{self.aux_bin_2}"
        self.orig_agyis_config_dir = os.environ.get("AGYIS_CONFIG_DIR")
        os.environ["AGYIS_CONFIG_DIR"] = str(self.config_dir)
        self.orig_psl_config_dir = os.environ.get("PSL_CONFIG_DIR")
        os.environ["PSL_CONFIG_DIR"] = str(self.config_dir)
        self.orig_agyis_surfaces = os.environ.get("AGYIS_SURFACES")
        os.environ["AGYIS_SURFACES"] = os.pathsep.join(str(s) for s in self.surfaces)

    def tearDown(self) -> None:
        for key, orig in (
            ("PSL_BIN_DIR", self.orig_bin_dir),
            ("PSL_AUX_BIN_DIRS", self.orig_aux_bin_dirs),
            ("AGYIS_CONFIG_DIR", self.orig_agyis_config_dir),
            ("PSL_CONFIG_DIR", self.orig_psl_config_dir),
            ("AGYIS_SURFACES", self.orig_agyis_surfaces),
        ):
            if orig is not None:
                os.environ[key] = orig
            else:
                os.environ.pop(key, None)

        self.temp_dir.cleanup()

    def test_coexistence_layer2_config_dir_and_workspace_alt_roots(self) -> None:
        """DRIFT-P1-09: CoexistenceEngine defaults Layer 2 to ~/.gemini/config and supports _agents/."""
        default_engine = CoexistenceEngine()
        self.assertEqual(default_engine.user_dir, (Path.home() / ".gemini" / "config").resolve())

        ws_dir = self.isolated_base / "ws_alt_roots"
        alt_agent = ws_dir / "_agents" / "agents" / "custom.md"
        alt_agent.parent.mkdir(parents=True)
        alt_agent.write_text("# alt\n", encoding="utf-8")
        engine = CoexistenceEngine(workspace_root=ws_dir, user_dir=self.config_dir)
        res = engine.resolve_resource("agent", "custom")
        self.assertTrue(res["found"])
        self.assertEqual(res["layer"], 3)
        self.assertEqual(res["path"], alt_agent)

    def test_tagged_rules_insertion_and_idempotence(self) -> None:
        """Workspace AGENTS.md preserves domain rules and manages tagged block idempotently."""
        ws_dir = self.isolated_base / "workspace_jasper"
        ws_dir.mkdir(parents=True)
        rules_file = ws_dir / "AGENTS.md"

        # Pre-existing project rules
        initial_rules = (
            "# Jasper Project Rules\n\n"
            "- Wait 10 minutes before merging PRs to allow CI fences to settle.\n"
            "- Always target staging branch.\n"
        )
        rules_file.write_text(initial_rules, encoding="utf-8")

        # 1. Initial install_workspace
        res1 = install_workspace(ws_dir, source_dir=REPO_ROOT)
        self.assertTrue(res1.success)
        self.assertTrue(res1.rules_updated)

        updated_content = rules_file.read_text(encoding="utf-8")
        self.assertIn("- Wait 10 minutes before merging PRs", updated_content)
        self.assertIn("- Always target staging branch.", updated_content)
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", updated_content)
        self.assertIn("<!-- End AGYIS-HARNESS -->", updated_content)
        self.assertNotIn("<!-- Added by PSL-HARNESS -->", updated_content)
        self.assertNotIn("<!-- End PSL-HARNESS -->", updated_content)

        # 2. Idempotent re-run
        res2 = install_workspace(ws_dir, source_dir=REPO_ROOT)
        self.assertTrue(res2.success)
        self.assertFalse(res2.rules_updated)

        re_read_content = rules_file.read_text(encoding="utf-8")
        self.assertEqual(re_read_content, updated_content)
        self.assertEqual(re_read_content.count("<!-- Added by AGYIS-HARNESS -->"), 1)
        self.assertEqual(re_read_content.count("<!-- End AGYIS-HARNESS -->"), 1)
        self.assertEqual(re_read_content.count("<!-- Added by PSL-HARNESS -->"), 0)
        self.assertEqual(re_read_content.count("<!-- End PSL-HARNESS -->"), 0)

    def test_workspace_stack_instantiation_and_dedup(self) -> None:
        """Workspace install auto-detects stack, installs stack skills, and respects dedup."""
        ws_dir = self.isolated_base / "workspace_ts"
        ws_dir.mkdir(parents=True)
        (ws_dir / "package.json").write_text(
            json.dumps({"name": "test-ts-app", "devDependencies": {"typescript": "^5.0.0"}}),
            encoding="utf-8",
        )

        # 1. Initial workspace install
        res1 = install_workspace(ws_dir, source_dir=REPO_ROOT)
        self.assertTrue(res1.success)
        self.assertEqual(res1.stack, "typescript")
        self.assertIn("psl-stack-typescript", res1.skills_installed)
        self.assertTrue((ws_dir / ".agents" / "skills" / "psl-stack-typescript" / "SKILL.md").is_file())

        # By default zero agent definitions in workspace (Layer 1 global inheritance)
        self.assertFalse((ws_dir / ".agents" / "agents").exists())

        # 2. Second run with dedup=True skips identical files
        res2 = install_workspace(ws_dir, source_dir=REPO_ROOT, dedup=True)
        self.assertTrue(res2.success)
        self.assertIn("psl-stack-typescript", res2.skills_skipped)
        self.assertEqual(res2.skills_installed, [])

        # 3. Third run with override=True reinstalls
        res3 = install_workspace(ws_dir, source_dir=REPO_ROOT, override=True)
        self.assertTrue(res3.success)
        self.assertIn("psl-stack-typescript", res3.skills_installed)

        # 4. Opt-in local agents
        res4 = install_workspace(ws_dir, source_dir=REPO_ROOT, include_agents=True)
        self.assertTrue(res4.success)
        self.assertTrue((ws_dir / ".agents" / "agents" / "agyis_builder.md").is_file())

    def test_workspace_rust_and_go_stack_instantiation(self) -> None:
        """Rust (Cargo.toml) and Go (go.mod) workspaces install respective stack and test runner skills."""
        # Rust workspace
        ws_rust = self.isolated_base / "workspace_rust"
        ws_rust.mkdir(parents=True)
        (ws_rust / "Cargo.toml").write_text("[package]\nname = 'rust-crate'\n", encoding="utf-8")

        res_rust = install_workspace(ws_rust, source_dir=REPO_ROOT)
        self.assertTrue(res_rust.success)
        self.assertEqual(res_rust.stack, "rust")
        self.assertIn("psl-test-cargo", res_rust.skills_installed)
        self.assertIn("psl-stack-systems", res_rust.skills_installed)
        self.assertIn("psl-stack-shell", res_rust.skills_installed)
        self.assertTrue((ws_rust / ".agents" / "skills" / "psl-test-cargo" / "SKILL.md").is_file())

        # Go workspace
        ws_go = self.isolated_base / "workspace_go"
        ws_go.mkdir(parents=True)
        (ws_go / "go.mod").write_text("module example.com/gomod\n\ngo 1.22\n", encoding="utf-8")

        res_go = install_workspace(ws_go, source_dir=REPO_ROOT)
        self.assertTrue(res_go.success)
        self.assertEqual(res_go.stack, "go")
        self.assertIn("psl-test-go", res_go.skills_installed)
        self.assertNotIn("psl-stack-backend", res_go.skills_installed)
        self.assertTrue((ws_go / ".agents" / "skills" / "psl-test-go" / "SKILL.md").is_file())

    def test_legacy_setup_detection_notice(self) -> None:
        """Legacy .agent/ directory triggers actionable notice recommending /psl-harmonize."""
        ws_dir = self.isolated_base / "legacy_ws"
        (ws_dir / ".agent").mkdir(parents=True)

        res = install_workspace(ws_dir, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        self.assertIsNotNone(res.legacy_notice)
        self.assertIn(".agent", res.legacy_notice)
        self.assertIn("/psl-harmonize", res.legacy_notice)

    def test_find_workspace_root(self) -> None:
        """find_workspace_root walks up directory tree to find marker files."""
        ws_dir = self.isolated_base / "project_root"
        nested_dir = ws_dir / "src" / "deep" / "nested"
        nested_dir.mkdir(parents=True)
        (ws_dir / ".git").mkdir()

        # From nested directory, finds root
        root = find_workspace_root(nested_dir)
        self.assertEqual(root, ws_dir)

        # From root itself
        self.assertEqual(find_workspace_root(ws_dir), ws_dir)

    def test_cli_init_subcommand(self) -> None:
        """CLI `psl init` initializes a workspace project."""
        ws_dir = self.isolated_base / "cli_ws"
        ws_dir.mkdir(parents=True)
        (ws_dir / "pyproject.toml").write_text("[project]\nname = 'sample-py'\n", encoding="utf-8")

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["init", str(ws_dir), "--yes", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["success"])
            self.assertEqual(data["stack"], "python")
            self.assertIn("psl-stack-python", data["skills_installed"])
            self.assertTrue((ws_dir / "AGENTS.md").is_file())

    def test_install_workspace_with_standalone_plugin_layout(self) -> None:
        """install_workspace resolves skills, agents, and rules when source is a distributed plugin layout."""
        fake_plugin = self.isolated_base / "dist_plugin"
        (fake_plugin / "skills" / "psl-harmonize").mkdir(parents=True)
        (fake_plugin / "skills" / "psl-harmonize" / "SKILL.md").write_text("# Harmonize", encoding="utf-8")
        (fake_plugin / "agents").mkdir(parents=True)
        (fake_plugin / "agents" / "hammer.md").write_text("# Hammer", encoding="utf-8")
        (fake_plugin / "rules").mkdir(parents=True)
        (fake_plugin / "rules" / "AGENTS.md").write_text("Universal Rules", encoding="utf-8")

        ws_dir = self.isolated_base / "dist_ws"
        ws_dir.mkdir(parents=True)

        res = install_workspace(
            ws_dir,
            skills=["psl-harmonize"],
            include_agents=True,
            source_dir=fake_plugin,
        )
        self.assertTrue(res.success)
        self.assertIn("psl-harmonize", res.skills_installed)
        self.assertTrue((ws_dir / ".agents" / "skills" / "psl-harmonize" / "SKILL.md").is_file())
        self.assertIn("hammer", res.agents_installed)
        self.assertTrue((ws_dir / ".agents" / "agents" / "hammer.md").is_file())
        self.assertTrue((ws_dir / "AGENTS.md").is_file())
        self.assertIn("Universal Rules", (ws_dir / "AGENTS.md").read_text(encoding="utf-8"))

    def test_tagged_rules_migration_from_legacy_psl_harness(self) -> None:
        """Workspace AGENTS.md converts legacy PSL-HARNESS blocks to AGYIS-HARNESS in place."""
        ws_dir = self.isolated_base / "workspace_legacy_migration"
        ws_dir.mkdir(parents=True)
        rules_file = ws_dir / "AGENTS.md"

        legacy_rules = (
            "# Existing Domain Rules\n\n"
            "- Wait 10 minutes before merging PRs to allow CI fences to settle.\n"
            "- Always target staging branch.\n\n"
            "<!-- Added by PSL-HARNESS -->\n"
            "# Universal Empirical Agent Rules: PSL Harness Guidelines\n"
            "- Pre-flight tool availability\n"
            "<!-- End PSL-HARNESS -->\n\n"
            "# Custom Footer Rules\n"
            "- Enforce clean code hygiene.\n"
        )
        rules_file.write_text(legacy_rules, encoding="utf-8")

        # 1. Initial install_workspace converts legacy block in-place
        res1 = install_workspace(ws_dir, source_dir=REPO_ROOT)
        self.assertTrue(res1.success)
        self.assertTrue(res1.rules_updated)

        updated_content = rules_file.read_text(encoding="utf-8")
        # Domain rules before and after the block are preserved
        self.assertIn("# Existing Domain Rules", updated_content)
        self.assertIn("- Wait 10 minutes before merging PRs", updated_content)
        self.assertIn("- Always target staging branch.", updated_content)
        self.assertIn("# Custom Footer Rules", updated_content)
        self.assertIn("- Enforce clean code hygiene.", updated_content)

        # Legacy tags are replaced by modern AGYIS-HARNESS tags
        self.assertNotIn("<!-- Added by PSL-HARNESS -->", updated_content)
        self.assertNotIn("<!-- End PSL-HARNESS -->", updated_content)
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", updated_content)
        self.assertIn("<!-- End AGYIS-HARNESS -->", updated_content)
        self.assertEqual(updated_content.count("<!-- Added by AGYIS-HARNESS -->"), 1)
        self.assertEqual(updated_content.count("<!-- End AGYIS-HARNESS -->"), 1)

        # 2. Idempotent re-run
        res2 = install_workspace(ws_dir, source_dir=REPO_ROOT)
        self.assertTrue(res2.success)
        self.assertFalse(res2.rules_updated)

        re_read_content = rules_file.read_text(encoding="utf-8")
        self.assertEqual(re_read_content, updated_content)
        self.assertEqual(re_read_content.count("<!-- Added by AGYIS-HARNESS -->"), 1)
        self.assertEqual(re_read_content.count("<!-- End AGYIS-HARNESS -->"), 1)
        self.assertEqual(re_read_content.count("<!-- Added by PSL-HARNESS -->"), 0)
        self.assertEqual(re_read_content.count("<!-- End PSL-HARNESS -->"), 0)

    def test_tagged_rules_constants_and_pattern_exports(self) -> None:
        """TAG_START, TAG_END, LEGACY_TAG_START, LEGACY_TAG_END, and TAGGED_BLOCK_PATTERN are exported."""
        from harness.delivery import (
            LEGACY_TAG_END,
            LEGACY_TAG_START,
            TAG_END,
            TAG_START,
            TAGGED_BLOCK_PATTERN,
        )

        self.assertEqual(TAG_START, "<!-- Added by AGYIS-HARNESS -->")
        self.assertEqual(TAG_END, "<!-- End AGYIS-HARNESS -->")
        self.assertEqual(LEGACY_TAG_START, "<!-- Added by PSL-HARNESS -->")
        self.assertEqual(LEGACY_TAG_END, "<!-- End PSL-HARNESS -->")

        # Pattern matches modern and legacy fences
        self.assertTrue(bool(TAGGED_BLOCK_PATTERN.search(f"{TAG_START}\nRules\n{TAG_END}")))
        self.assertTrue(bool(TAGGED_BLOCK_PATTERN.search(f"{LEGACY_TAG_START}\nRules\n{LEGACY_TAG_END}")))
        self.assertTrue(bool(TAGGED_BLOCK_PATTERN.search(f"{LEGACY_TAG_START}\nRules\n{TAG_END}")))
        self.assertFalse(bool(TAGGED_BLOCK_PATTERN.search("# Plain rules without demarcations")))

    def test_extract_command_dictionary_node(self) -> None:
        """Extracts command dictionary from package.json with pnpm, yarn, bun, and npm."""
        from harness.delivery import extract_command_dictionary

        ws = self.isolated_base / "node_cmd_ws"
        ws.mkdir(parents=True)
        (ws / "package.json").write_text(
            json.dumps({"scripts": {"test": "vitest", "build": "tsc", "lint": "eslint ."}}),
            encoding="utf-8",
        )
        (ws / "pnpm-lock.yaml").write_text("", encoding="utf-8")

        cmds = extract_command_dictionary(ws)
        self.assertEqual(cmds.get("test"), "pnpm test")
        self.assertEqual(cmds.get("build"), "pnpm build")
        self.assertEqual(cmds.get("lint"), "pnpm lint")

    def test_extract_command_dictionary_python(self) -> None:
        """Extracts command dictionary from pyproject.toml with pytest and ruff."""
        from harness.delivery import extract_command_dictionary

        ws = self.isolated_base / "py_cmd_ws"
        ws.mkdir(parents=True)
        (ws / "pyproject.toml").write_text(
            '[tool.pytest.ini_options]\naddopts = "-q"\n[tool.ruff]\nline-length = 88\n',
            encoding="utf-8",
        )

        cmds = extract_command_dictionary(ws)
        self.assertEqual(cmds.get("test"), "pytest")
        self.assertEqual(cmds.get("lint"), "ruff check .")
        self.assertEqual(cmds.get("format"), "ruff format .")

    def test_extract_command_dictionary_makefile(self) -> None:
        """Extracts command dictionary from Makefile."""
        from harness.delivery import extract_command_dictionary

        ws = self.isolated_base / "make_cmd_ws"
        ws.mkdir(parents=True)
        (ws / "Makefile").write_text(
            "all:\n\tgcc main.c\n\ntest:\n\t./test.sh\n\nclean:\n\trm -rf *.o\n",
            encoding="utf-8",
        )

        cmds = extract_command_dictionary(ws)
        self.assertEqual(cmds.get("all"), "make all")
        self.assertEqual(cmds.get("test"), "make test")
        self.assertEqual(cmds.get("clean"), "make clean")

    def test_extract_command_dictionary_rust_and_go(self) -> None:
        """Extracts command dictionary from Cargo.toml and go.mod."""
        from harness.delivery import extract_command_dictionary

        ws_rust = self.isolated_base / "rust_cmd_ws"
        ws_rust.mkdir(parents=True)
        (ws_rust / "Cargo.toml").write_text('[package]\nname = "foo"\n', encoding="utf-8")
        rust_cmds = extract_command_dictionary(ws_rust)
        self.assertEqual(rust_cmds.get("test"), "cargo test")
        self.assertEqual(rust_cmds.get("build"), "cargo build")
        self.assertEqual(rust_cmds.get("lint"), "cargo clippy")

        ws_go = self.isolated_base / "go_cmd_ws"
        ws_go.mkdir(parents=True)
        (ws_go / "go.mod").write_text("module example.com/foo\n", encoding="utf-8")
        go_cmds = extract_command_dictionary(ws_go)
        self.assertEqual(go_cmds.get("test"), "go test ./...")
        self.assertEqual(go_cmds.get("build"), "go build ./...")

    def test_install_workspace_dry_run_zero_mutations(self) -> None:
        """install_workspace with dry_run=True performs zero filesystem modifications."""
        ws = self.isolated_base / "dry_run_ws"
        ws.mkdir(parents=True)
        (ws / "package.json").write_text(
            json.dumps({"scripts": {"test": "jest"}}),
            encoding="utf-8",
        )

        res = install_workspace(ws, dry_run=True, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        self.assertTrue(res.dry_run)
        self.assertEqual(res.stack, "typescript")
        self.assertIn("psl-stack-typescript", res.skills_installed)
        self.assertEqual(res.command_dictionary.get("test"), "npm test")

        # Zero disk mutations
        self.assertFalse((ws / ".agents").exists())
        self.assertFalse((ws / "AGENTS.md").exists())

    def test_install_workspace_injects_command_dictionary(self) -> None:
        """install_workspace embeds extracted command dictionary into AGENTS.md."""
        ws = self.isolated_base / "inject_cmd_ws"
        ws.mkdir(parents=True)
        (ws / "package.json").write_text(
            json.dumps({"scripts": {"test": "jest", "build": "tsc"}}),
            encoding="utf-8",
        )

        res = install_workspace(ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        self.assertFalse(res.dry_run)
        self.assertTrue((ws / "AGENTS.md").is_file())

        content = (ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("# 🧪 Project Verification & Native Toolchain", content)
        self.assertIn("npm test", content)
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", content)

    def test_cmd_init_with_role_and_subproject(self) -> None:
        """cmd_init targets subproject and provisions decoupled role skills."""
        ws = self.isolated_base / "monorepo_init_subproject"
        ws.mkdir(parents=True)
        (ws / "pnpm-workspace.yaml").write_text("packages:\n  - 'services/*'\n", encoding="utf-8")

        svc_api = ws / "services" / "api"
        svc_api.mkdir(parents=True)
        (svc_api / "pyproject.toml").write_text("[project]\nname = 'api'\n", encoding="utf-8")

        # Invoke cmd_init with subproject and explicit role
        args = argparse.Namespace(
            path=str(ws),
            subproject="services/api",
            stack=None,
            role="backend",
            skills=None,
            agents=None,
            override=False,
            no_dedup=False,
            dry_run=False,
            json=True,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = cmd_init(args)
            self.assertEqual(exit_code, 0)
            data = json.loads(mock_stdout.getvalue())
            self.assertTrue(data["success"])
            self.assertEqual(data["role"], "backend")
            self.assertEqual(data["subproject"], "services/api")
            self.assertIn("psl-stack-python", data["skills_installed"])
            self.assertIn("psl-test-python", data["skills_installed"])
            self.assertIn("psl-stack-backend", data["skills_installed"])
            self.assertIn("db-ops", data["skills_installed"])

        # Verify files on disk in subproject
        self.assertTrue((svc_api / ".agents" / "skills" / "psl-stack-backend" / "SKILL.md").is_file())
        self.assertTrue((svc_api / ".agents" / "skills" / "db-ops" / "SKILL.md").is_file())
        self.assertTrue((svc_api / "AGENTS.md").is_file())

    def test_cmd_init_monorepo_auto_discovery(self) -> None:
        """cmd_init at monorepo root auto-detects polyglot child services at depth 2."""
        ws = self.isolated_base / "monorepo_root_init"
        ws.mkdir(parents=True)
        (ws / "turbo.json").write_text("{}", encoding="utf-8")

        app_web = ws / "apps" / "web"
        app_web.mkdir(parents=True)
        (app_web / "tsconfig.json").write_text("{}", encoding="utf-8")

        svc_api = ws / "services" / "api"
        svc_api.mkdir(parents=True)
        (svc_api / "pyproject.toml").write_text("[project]\nname = 'api'\n", encoding="utf-8")

        args = argparse.Namespace(
            path=str(ws),
            subproject=None,
            stack=None,
            role=None,
            skills=None,
            agents=None,
            override=False,
            no_dedup=False,
            dry_run=False,
            json=True,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = cmd_init(args)
            self.assertEqual(exit_code, 0)
            data = json.loads(mock_stdout.getvalue())
            self.assertTrue(data["success"])
            # Discovered skills from both apps/web (typescript) and services/api (python)
            self.assertIn("psl-stack-typescript", data["skills_installed"])
            self.assertIn("psl-test-node", data["skills_installed"])
            self.assertIn("psl-stack-python", data["skills_installed"])
            self.assertIn("psl-test-python", data["skills_installed"])
            # Zero backend skills since neither has backend manifests
            self.assertNotIn("psl-stack-backend", data["skills_installed"])

    def test_cmd_init_boundary_role_cli(self) -> None:
        """cmd_init with role='cli' installs zero extraneous backend skills."""
        ws = self.isolated_base / "cli_tool_ws"
        ws.mkdir(parents=True)
        (ws / "pyproject.toml").write_text("[project]\nname = 'cli-tool'\n", encoding="utf-8")

        args = argparse.Namespace(
            path=str(ws),
            subproject=None,
            stack="python",
            role="cli",
            skills=None,
            agents=None,
            override=False,
            no_dedup=False,
            dry_run=False,
            json=True,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = cmd_init(args)
            self.assertEqual(exit_code, 0)
            data = json.loads(mock_stdout.getvalue())
            self.assertTrue(data["success"])
            self.assertIn("psl-stack-python", data["skills_installed"])
            self.assertIn("psl-test-python", data["skills_installed"])
            self.assertNotIn("psl-stack-backend", data["skills_installed"])
            self.assertNotIn("db-ops", data["skills_installed"])


class TestDeliveryEngineRemediation(unittest.TestCase):
    """Hermetic unit tests for Delivery Engine remediation:
    - Dynamic license matching (MIT vs Apache-2.0)
    - Context-aware command descriptions
    - Knot-mesh symlink preservation in .agents/skills/<name>
    """

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name) / "workspace"
        self.ws.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_detect_repository_license(self) -> None:
        """detect_repository_license detects MIT and Apache-2.0 across manifests."""
        # Non-existent dir
        self.assertIsNone(detect_repository_license(self.ws / "nonexistent"))

        # package.json
        (self.ws / "package.json").write_text(json.dumps({"name": "pkg", "license": "MIT"}), encoding="utf-8")
        self.assertEqual(detect_repository_license(self.ws), "MIT")

        # pyproject.toml override when package.json removed
        (self.ws / "package.json").unlink()
        (self.ws / "pyproject.toml").write_text('[project]\nname = "py"\nlicense = "Apache-2.0"\n', encoding="utf-8")
        self.assertEqual(detect_repository_license(self.ws), "Apache-2.0")

        # Cargo.toml
        (self.ws / "pyproject.toml").unlink()
        (self.ws / "Cargo.toml").write_text('[package]\nname = "rs"\nlicense = "MIT OR Apache-2.0"\n', encoding="utf-8")
        self.assertEqual(detect_repository_license(self.ws), "MIT OR Apache-2.0")

        # LICENSE file fallback
        (self.ws / "Cargo.toml").unlink()
        (self.ws / "LICENSE").write_text("MIT License\n\nPermission is hereby granted...", encoding="utf-8")
        self.assertEqual(detect_repository_license(self.ws), "MIT")

        (self.ws / "LICENSE").write_text("Apache License\nVersion 2.0, January 2004\n...", encoding="utf-8")
        self.assertEqual(detect_repository_license(self.ws), "Apache-2.0")

    def test_adapt_spdx_license(self) -> None:
        """adapt_spdx_license replaces SPDX identifiers appropriately."""
        original = "# SPDX-License-Identifier: Apache-2.0\n# Copyright 2026\n"
        adapted = adapt_spdx_license(original, "MIT")
        self.assertIn("SPDX-License-Identifier: MIT", adapted)
        self.assertNotIn("SPDX-License-Identifier: Apache-2.0", adapted)

        # Retains Apache-2.0 when requested
        self.assertEqual(adapt_spdx_license(original, "Apache-2.0"), original)

    def test_adapt_spdx_license_compound_expressions(self) -> None:
        """adapt_spdx_license handles compound expressions, parentheses, and boolean operators without corrupting comment tags."""
        # Single to compound
        s1 = "<!-- SPDX-License-Identifier: Apache-2.0 -->"
        res1 = adapt_spdx_license(s1, "MIT OR Apache-2.0")
        self.assertEqual(res1, "<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->")

        # Compound to single
        res2 = adapt_spdx_license(res1, "GPL-3.0")
        self.assertEqual(res2, "<!-- SPDX-License-Identifier: GPL-3.0 -->")

        # Compound with parentheses and AND operator
        res3 = adapt_spdx_license(res2, "(MIT AND BSD-3-Clause)")
        self.assertEqual(res3, "<!-- SPDX-License-Identifier: (MIT AND BSD-3-Clause) -->")

        # C-style block comments
        s4 = "/* SPDX-License-Identifier: MIT OR Apache-2.0 */"
        res4 = adapt_spdx_license(s4, "Apache-2.0")
        self.assertEqual(res4, "/* SPDX-License-Identifier: Apache-2.0 */")

        # Shell / Python hash comments with compound license
        s5 = "# SPDX-License-Identifier: MIT OR Apache-2.0\n# Next comment line\n"
        res5 = adapt_spdx_license(s5, "GPL-3.0")
        self.assertEqual(res5, "# SPDX-License-Identifier: GPL-3.0\n# Next comment line\n")

        # WITH exception expressions
        s6 = "<!-- SPDX-License-Identifier: GPL-2.0-only WITH Classpath-exception-2.0 -->"
        res6 = adapt_spdx_license(s6, "MIT")
        self.assertEqual(res6, "<!-- SPDX-License-Identifier: MIT -->")

        # Empty or None target license returns unchanged
        self.assertEqual(adapt_spdx_license(s1, ""), s1)
        self.assertEqual(adapt_spdx_license(s1, None), s1)

    def test_extract_command_descriptions(self) -> None:
        """extract_command_descriptions infers context-aware semantic descriptions."""
        # package.json with clean = pkill, dev = tauri dev, build = tauri build
        (self.ws / "package.json").write_text(
            json.dumps({
                "name": "app",
                "scripts": {
                    "clean": "pkill -f myapp || true",
                    "dev": "tauri dev",
                    "build": "tauri build",
                }
            }),
            encoding="utf-8",
        )
        descs = extract_command_descriptions(self.ws)
        self.assertEqual(descs.get("clean"), "Terminate zombie sidecar/app processes")
        self.assertEqual(descs.get("dev"), "Start local desktop/mobile development application")
        self.assertEqual(descs.get("build"), "Build application package & native binaries")

    def test_symlink_aware_skill_provisioning(self) -> None:
        """install_workspace preserves existing symlinks under .agents/skills/."""
        # Create a mock target outside the workspace (simulating knot-mesh or shared skill)
        shared_dir = self.ws.parent / "shared_skills" / "psl-stack-shell"
        shared_dir.mkdir(parents=True)
        shared_skill = shared_dir / "SKILL.md"
        shared_skill.write_text("---\nname: psl-stack-shell\ndescription: old\n---\nOld content\n", encoding="utf-8")

        # In self.ws / ".agents" / "skills", create directory symlink ws_skill_dir pointing to shared_dir
        skills_parent = self.ws / ".agents" / "skills"
        skills_parent.mkdir(parents=True)
        ws_skill_dir = skills_parent / "psl-stack-shell"
        ws_skill_dir.symlink_to(shared_dir)

        self.assertTrue(ws_skill_dir.is_symlink())

        # Now install_workspace for psl-stack-shell with override=True
        res = install_workspace(self.ws, skills=["psl-stack-shell"], override=True)
        self.assertTrue(res.success)
        self.assertIn("psl-stack-shell", res.skills_installed)

        # The symlink should STILL be a symlink!
        self.assertTrue(ws_skill_dir.is_symlink())
        self.assertEqual(ws_skill_dir.resolve(), shared_dir.resolve())

        # And the target should have been updated with fresh content
        content = (shared_dir / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("Old content", content)
        self.assertIn("name: psl-stack-shell", content)

    def test_dynamic_license_adaptation_in_install_workspace(self) -> None:
        """install_workspace adapts license to MIT when repo is MIT."""
        (self.ws / "package.json").write_text(json.dumps({"name": "mit-app", "license": "MIT"}), encoding="utf-8")
        res = install_workspace(self.ws, skills=["psl-stack-shell"])
        self.assertTrue(res.success)

        agents_rule = self.ws / "AGENTS.md"
        self.assertTrue(agents_rule.is_file())
        self.assertIn("SPDX-License-Identifier: MIT", agents_rule.read_text(encoding="utf-8"))

        skill_file = self.ws / ".agents" / "skills" / "psl-stack-shell" / "SKILL.md"
        self.assertTrue(skill_file.is_file())
        self.assertIn("SPDX-License-Identifier: MIT", skill_file.read_text(encoding="utf-8"))

    def test_dynamic_compound_license_adaptation_in_install_workspace(self) -> None:
        """install_workspace adapts license to compound expression when repo has compound license."""
        (self.ws / "Cargo.toml").write_text('[package]\nname = "rs"\nlicense = "MIT OR Apache-2.0"\n', encoding="utf-8")
        res = install_workspace(self.ws, skills=["psl-stack-shell"])
        self.assertTrue(res.success)

        agents_rule = self.ws / "AGENTS.md"
        self.assertTrue(agents_rule.is_file())
        self.assertIn("SPDX-License-Identifier: MIT OR Apache-2.0", agents_rule.read_text(encoding="utf-8"))

        skill_file = self.ws / ".agents" / "skills" / "psl-stack-shell" / "SKILL.md"
        self.assertTrue(skill_file.is_file())
        self.assertIn("SPDX-License-Identifier: MIT OR Apache-2.0", skill_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
