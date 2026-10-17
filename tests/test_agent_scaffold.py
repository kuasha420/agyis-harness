#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic unit and integration tests for PSL Agent Scaffolding & Validation Engine (ADR-026).

Tests:
- Capability bundle hierarchies and ANTIGRAVITY_PLATFORM_TOOLS membership
- Workspace context inspection across package manifests
- Deterministic Markdown scaffolding with hybrid grounding
- Validation gate: invalid tool rejection, contradiction checks, invariant enforcement
- CLI 'agents create' and 'agents validate' end-to-end execution
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from harness.cli import main
from harness.skills import parse_frontmatter
from harness.subagents import (
    ANTIGRAVITY_PLATFORM_TOOLS,
    CAPABILITY_BUNDLES,
    REPO_ROOT,
    AgentArchetype,
    ToolPermissions,
    inspect_workspace_context,
    load_agent_spec,
    scaffold_agent_markdown,
    validate_agent_spec,
)


class TestAgentScaffoldAndValidation(unittest.TestCase):
    """Test suite for agent generator, validator, and CLI commands."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_platform_tools_and_capability_bundles(self) -> None:
        """Every tool in capability bundles must exist in ANTIGRAVITY_PLATFORM_TOOLS."""
        self.assertIn("read_only", CAPABILITY_BUNDLES)
        self.assertIn("verifier", CAPABILITY_BUNDLES)
        self.assertIn("adversarial_verifier", CAPABILITY_BUNDLES)
        self.assertIn("builder", CAPABILITY_BUNDLES)
        self.assertIn("orchestrator", CAPABILITY_BUNDLES)
        self.assertIn("full", CAPABILITY_BUNDLES)

        for bundle_name, tools in CAPABILITY_BUNDLES.items():
            for tool in tools:
                self.assertIn(
                    tool,
                    ANTIGRAVITY_PLATFORM_TOOLS,
                    f"Tool '{tool}' in bundle '{bundle_name}' not in ANTIGRAVITY_PLATFORM_TOOLS",
                )

        # Bundle hierarchies
        read_only = set(CAPABILITY_BUNDLES["read_only"])
        verifier = set(CAPABILITY_BUNDLES["verifier"])
        builder = set(CAPABILITY_BUNDLES["builder"])
        orchestrator = set(CAPABILITY_BUNDLES["orchestrator"])
        full = set(CAPABILITY_BUNDLES["full"])

        self.assertTrue(read_only.issubset(verifier))
        self.assertTrue(verifier.issubset(builder))
        self.assertTrue(read_only.issubset(orchestrator))
        self.assertTrue(builder.issubset(full))
        self.assertTrue(orchestrator.issubset(full))
        self.assertEqual(full, ANTIGRAVITY_PLATFORM_TOOLS)

        self.assertIn("run_command", verifier)
        self.assertIn("write_to_file", builder)
        self.assertIn("replace_file_content", builder)
        self.assertIn("invoke_subagent", orchestrator)
        self.assertNotIn("write_to_file", orchestrator)
        self.assertIn("write_to_file", full)
        self.assertIn("invoke_subagent", full)
        self.assertEqual(len(full), len(ANTIGRAVITY_PLATFORM_TOOLS))

    def test_inspect_workspace_context_repo_root(self) -> None:
        """inspect_workspace_context successfully parses current repo project files."""
        ctx = inspect_workspace_context(REPO_ROOT)
        self.assertEqual(ctx["project_name"], "agyis-harness")
        self.assertIn("Python", ctx["languages"])
        self.assertIn("pytest", ctx["test_runners"])
        self.assertIn("pyproject.toml", ctx["detected_files"])
        self.assertIn("package.json", ctx["detected_files"])
        self.assertIsInstance(ctx["commands"], list)
        self.assertIsInstance(ctx["rules"], list)

    def test_inspect_workspace_context_isolated(self) -> None:
        """inspect_workspace_context parses Cargo.toml, AGENTS.md, and matrix.json."""
        (self.workspace / "Cargo.toml").write_text(
            '[package]\nname = "my-rust-crate"\nversion = "0.1.0"\n', encoding="utf-8"
        )
        (self.workspace / "AGENTS.md").write_text(
            "# Rules\n- Rule 1: Zero error swallowing\n- Rule 2: Hermetic tests\n",
            encoding="utf-8",
        )
        (self.workspace / "matrix.json").write_text(
            json.dumps({"python": "3.12", "shell": "bash"}), encoding="utf-8"
        )

        ctx = inspect_workspace_context(self.workspace)
        self.assertEqual(ctx["project_name"], "my-rust-crate")
        self.assertIn("Rust", ctx["languages"])
        self.assertIn("cargo test", ctx["test_runners"])
        self.assertTrue(any("Zero error swallowing" in r for r in ctx["rules"]))
        self.assertIn("Cargo.toml", ctx["detected_files"])
        self.assertIn("AGENTS.md", ctx["detected_files"])
        self.assertIn("matrix.json", ctx["detected_files"])

    def test_inspect_workspace_context_esm(self) -> None:
        """inspect_workspace_context detects is_esm and module_format when type is module."""
        (self.workspace / "package.json").write_text(
            json.dumps({"name": "esm-pkg", "type": "module"}),
            encoding="utf-8",
        )
        ctx = inspect_workspace_context(self.workspace)
        self.assertTrue(ctx["is_esm"])
        self.assertEqual(ctx["module_format"], "module")

        # When package.json does not specify type module
        (self.workspace / "package.json").write_text(
            json.dumps({"name": "cjs-pkg"}),
            encoding="utf-8",
        )
        ctx_cjs = inspect_workspace_context(self.workspace)
        self.assertFalse(ctx_cjs["is_esm"])
        self.assertEqual(ctx_cjs["module_format"], "commonjs")

    def test_scaffold_agent_markdown_structure(self) -> None:
        """scaffold_agent_markdown generates valid YAML frontmatter and hybrid prompt."""
        ws_ctx = {
            "project_name": "sample-project",
            "languages": ["Python", "TypeScript"],
            "test_runners": ["pytest"],
            "commands": ["test", "lint"],
            "rules": ["Enforce strict types"],
        }
        md = scaffold_agent_markdown(
            name="custom_worker",
            archetype=AgentArchetype.EXECUTIONER,
            workspace_context=ws_ctx,
            custom_instructions="Focus on performance.",
        )

        self.assertTrue(md.startswith("---"))
        fm, prompt = parse_frontmatter(md)
        self.assertEqual(fm["name"], "custom_worker")
        self.assertEqual(fm["archetype"], "executioner")
        self.assertTrue(fm["subagent"])
        self.assertTrue(fm["mainAgent"])
        self.assertTrue(fm.get("inheritCustomizations"))
        self.assertEqual(fm["model"], "inherit")
        self.assertTrue(fm["permissions"]["write"])
        self.assertTrue(fm["permissions"]["execute"])
        self.assertFalse(fm["permissions"]["subagents"])

        # Check hybrid grounding in body
        self.assertIn("sample-project", prompt)
        self.assertIn("Python, TypeScript", prompt)
        self.assertIn("Enforce strict types", prompt)
        self.assertIn("Zero-Exploration Invariant", prompt)
        self.assertIn("Focus on performance.", prompt)

    def test_main_archetype_scaffold_and_validation(self) -> None:
        """Main archetype scaffolding generates full bundle, permissions, invariants, and passes validation."""
        md = scaffold_agent_markdown(name="test_psl_lead", archetype=AgentArchetype.MAIN)
        self.assertTrue(md.startswith("---"))
        fm, prompt = parse_frontmatter(md)

        self.assertEqual(fm["name"], "test_psl_lead")
        self.assertEqual(fm["archetype"], "main")
        self.assertTrue(fm["subagent"])
        self.assertTrue(fm["mainAgent"])
        self.assertTrue(fm["inheritCustomizations"])
        self.assertEqual(fm["model"], "inherit")

        # Full permissions
        perms = fm["permissions"]
        self.assertTrue(perms["read"])
        self.assertTrue(perms["write"])
        self.assertTrue(perms["execute"])
        self.assertTrue(perms["subagents"])
        self.assertTrue(perms["mcp"])
        self.assertTrue(perms.get("enable_write_tools"))

        # All 20 platform tools in tools & allowed_tools
        self.assertEqual(len(fm["tools"]), len(ANTIGRAVITY_PLATFORM_TOOLS))
        self.assertEqual(set(fm["tools"]), ANTIGRAVITY_PLATFORM_TOOLS)
        self.assertEqual(set(fm["allowed_tools"]), ANTIGRAVITY_PLATFORM_TOOLS)

        # Invariants in prompt
        self.assertIn("The 5 Ground Rules", prompt)
        self.assertIn("agyis test", prompt)
        self.assertIn("agyis doctor", prompt)
        self.assertIn("agyis status", prompt)
        self.assertIn("agyis sync", prompt)
        self.assertIn("ADR-012", prompt)
        self.assertIn("ADR-013", prompt)
        self.assertIn("ADR-014", prompt)
        self.assertIn("ADR-015", prompt)
        self.assertIn("@<subagent>", prompt)
        self.assertIn("Zero-Exploration Invariant", prompt)
        self.assertIn("list_dir", prompt)
        self.assertIn("find_by_name", prompt)

        # Validate with validate_agent_spec
        spec_path = self.workspace / "test_psl_lead.md"
        spec_path.write_text(md, encoding="utf-8")
        errors = validate_agent_spec(spec_path)
        self.assertEqual(errors, [], f"Validation failed for test_psl_lead: {errors}")

    def test_planner_archetype_scaffold_tools_and_permissions(self) -> None:
        """Planner archetype scaffolds with write, subagent permissions and artifact synthesis tools."""
        md = scaffold_agent_markdown(name="test_planner", archetype=AgentArchetype.PLANNER)
        fm, prompt = parse_frontmatter(md)
        self.assertEqual(fm["archetype"], "planner")
        self.assertTrue(fm["permissions"]["write"])
        self.assertTrue(fm["permissions"]["subagents"])
        for expected_tool in [
            "write_to_file",
            "ask_question",
            "invoke_subagent",
            "send_message",
            "manage_subagents",
        ]:
            self.assertIn(expected_tool, fm["tools"])
            self.assertIn(expected_tool, fm["allowed_tools"])
        self.assertIn("Artifact-First Planning", prompt)

        # Validate spec
        spec_path = self.workspace / "test_planner.md"
        spec_path.write_text(md, encoding="utf-8")
        errors = validate_agent_spec(spec_path)
        self.assertEqual(errors, [], f"Validation failed for test_planner: {errors}")

    def test_custodian_archetype_scaffold_tools_and_permissions(self) -> None:
        """Custodian archetype scaffolds with verifier bundle, exec tools, write: false, and enable_write_tools: false."""
        md = scaffold_agent_markdown(name="test_custodian", archetype=AgentArchetype.CUSTODIAN)
        fm, prompt = parse_frontmatter(md)
        self.assertEqual(fm["archetype"], "custodian")
        self.assertFalse(fm["permissions"]["write"])
        self.assertTrue(fm["permissions"]["execute"])
        self.assertFalse(fm["permissions"].get("enable_write_tools", False))
        self.assertFalse(fm["permissions"]["subagents"])
        self.assertIn("run_command", fm["tools"])
        self.assertNotIn("write_to_file", fm["tools"])
        self.assertIn("Macro Review & Deduplication Mandate", prompt)
        self.assertIn("Targeted Macro & Deduplication Sweep Invariant", prompt)

        # Validate spec
        spec_path = self.workspace / "test_custodian.md"
        spec_path.write_text(md, encoding="utf-8")
        errors = validate_agent_spec(spec_path)
        self.assertEqual(errors, [], f"Validation failed for test_custodian: {errors}")

    def test_inherit_customizations_parsing_round_trip_and_validation(self) -> None:
        """inheritCustomizations parses correctly, round trips, and validates boolean constraint."""
        # 1. Parsing when true
        p_true = self.workspace / "agent_true.md"
        p_true.write_text(
            scaffold_agent_markdown("agent_true", AgentArchetype.EXECUTIONER, inherit_customizations=True),
            encoding="utf-8",
        )
        spec_true = load_agent_spec(p_true)
        self.assertTrue(spec_true.inherit_customizations)
        self.assertEqual(validate_agent_spec(p_true), [])

        # 2. Parsing when false
        p_false = self.workspace / "agent_false.md"
        p_false.write_text(
            scaffold_agent_markdown("agent_false", AgentArchetype.EXECUTIONER, inherit_customizations=False),
            encoding="utf-8",
        )
        spec_false = load_agent_spec(p_false)
        self.assertFalse(spec_false.inherit_customizations)
        self.assertEqual(validate_agent_spec(p_false), [])

        # 3. Parsing when omitted
        raw_omitted = """---
name: agent_omitted
archetype: hammer
description: Omitted inheritance test.
role: Reviewer
subagent: true
mainAgent: true
model: inherit
permissions:
  read: true
  write: false
  execute: false
  subagents: false
tools:
  - view_file
allowed_tools:
  - view_file
---

# Reviewer
You are `agent_omitted`.
## Operational Invariants
1. Zero-Exploration Invariant: Prohibit blind list_dir and find_by_name sweeps.
"""
        p_omitted = self.workspace / "agent_omitted.md"
        p_omitted.write_text(raw_omitted, encoding="utf-8")
        spec_omitted = load_agent_spec(p_omitted)
        self.assertTrue(spec_omitted.inherit_customizations, "Should default to True when omitted")
        self.assertEqual(validate_agent_spec(p_omitted), [])

        # 4. Validation rejects non-boolean inheritCustomizations
        raw_invalid = """---
name: agent_invalid
archetype: hammer
description: Invalid inheritance test.
role: Reviewer
subagent: true
mainAgent: true
inheritCustomizations: "non_boolean_string"
model: inherit
permissions:
  read: true
  write: false
  execute: false
  subagents: false
tools:
  - view_file
allowed_tools:
  - view_file
---

# Reviewer
You are `agent_invalid`.
## Operational Invariants
1. Zero-Exploration Invariant: Prohibit blind list_dir and find_by_name sweeps.
"""
        p_invalid = self.workspace / "agent_invalid.md"
        p_invalid.write_text(raw_invalid, encoding="utf-8")
        errors = validate_agent_spec(p_invalid)
        self.assertTrue(any("inheritCustomizations' must be a boolean" in e for e in errors))

    def test_validate_agent_spec_accepts_valid_scaffold(self) -> None:
        """Generated agents from scaffold_agent_markdown pass validation with zero errors."""
        for arch in AgentArchetype:
            with self.subTest(archetype=arch.value):
                md = scaffold_agent_markdown(name=f"test_{arch.value}", archetype=arch)
                spec_path = self.workspace / f"test_{arch.value}.md"
                spec_path.write_text(md, encoding="utf-8")

                errors = validate_agent_spec(spec_path)
                self.assertEqual(errors, [], f"Validation failed for {arch.value}: {errors}")

    def test_validate_agent_spec_rejects_unknown_tools(self) -> None:
        """Rejects agent specs declaring tools not in ANTIGRAVITY_PLATFORM_TOOLS."""
        invalid_md = """---
name: bad_agent
archetype: hammer
description: Invalid tool test.
role: Reviewer
subagent: true
mainAgent: true
model: inherit
permissions:
  read: true
  write: false
  execute: false
  subagents: false
tools:
  - view_file
  - imaginary_nonexistent_tool
allowed_tools:
  - view_file
  - imaginary_nonexistent_tool
---

# Reviewer

You are `bad_agent`.

## Operational Invariants
1. Zero-Exploration Invariant: Prohibit blind list_dir and find_by_name sweeps.
"""
        bad_path = self.workspace / "bad_agent.md"
        bad_path.write_text(invalid_md, encoding="utf-8")

        errors = validate_agent_spec(bad_path)
        self.assertTrue(any("imaginary_nonexistent_tool" in e for e in errors))

    def test_validate_agent_spec_rejects_mcp_tools(self) -> None:
        """Rejects agent specs declaring MCP tools statically in tools or allowed_tools."""
        mcp_md = """---
name: mcp_agent
archetype: main
description: MCP tool declaration test.
role: PSL Lead Architect & Master Implementer
subagent: true
mainAgent: true
model: inherit
permissions:
  read: true
  write: true
  execute: true
  subagents: true
  mcp: true
tools:
  - view_file
  - call_mcp_tool
allowed_tools:
  - view_file
  - call_mcp_tool
---

# PSL Lead Architect & Master Implementer
You are `mcp_agent`.
## Operational Invariants
1. Zero-Exploration Invariant: Prohibit blind list_dir and find_by_name sweeps.
"""
        mcp_path = self.workspace / "mcp_agent.md"
        mcp_path.write_text(mcp_md, encoding="utf-8")
        errors = validate_agent_spec(mcp_path)
        self.assertTrue(
            any("MCP tools (call_mcp_tool, list_resources, read_resource) cannot be listed" in e for e in errors),
            f"Expected MCP tool rejection error, got: {errors}",
        )

    def test_validate_agent_spec_detects_contradictions(self) -> None:
        """Rejects agent specs declaring write tools when permissions.write is false."""
        contradictory_md = """---
name: liar_agent
archetype: hammer
description: Contradictory permission test.
role: Reviewer
subagent: true
mainAgent: true
model: inherit
permissions:
  read: true
  write: false
  execute: false
  subagents: false
tools:
  - view_file
  - write_to_file
allowed_tools:
  - view_file
  - write_to_file
---

# Reviewer

You are `liar_agent`.

## Operational Invariants
1. Zero-Exploration Invariant: Prohibit blind list_dir and find_by_name sweeps.
"""
        c_path = self.workspace / "liar_agent.md"
        c_path.write_text(contradictory_md, encoding="utf-8")

        errors = validate_agent_spec(c_path)
        self.assertTrue(any("Contradiction: agent has 'write: false'" in e for e in errors))

        # Rejects write: false with enable_write_tools: true
        paradox_md = """---
name: paradox_agent
archetype: hammer
description: Contradictory enable_write_tools test.
role: Reviewer
subagent: true
mainAgent: true
model: inherit
permissions:
  read: true
  write: false
  execute: false
  subagents: false
  enable_write_tools: true
tools:
  - view_file
allowed_tools:
  - view_file
---

# Reviewer

You are `paradox_agent`.

## Operational Invariants
1. Zero-Exploration Invariant: Prohibit blind list_dir and find_by_name sweeps.
"""
        p_path = self.workspace / "paradox_agent.md"
        p_path.write_text(paradox_md, encoding="utf-8")
        errors2 = validate_agent_spec(p_path)
        self.assertTrue(any("Contradiction: agent has 'write: false' but 'enable_write_tools: true'" in e for e in errors2))

    def test_validate_agent_spec_requires_zero_exploration_invariant(self) -> None:
        """Rejects agent specs that do not enforce the Zero-Exploration Invariant."""
        no_zero_expl = """---
name: careless_agent
archetype: hammer
description: Missing invariant test.
role: Reviewer
subagent: true
mainAgent: true
model: inherit
permissions:
  read: true
  write: false
  execute: false
  subagents: false
tools:
  - view_file
allowed_tools:
  - view_file
---

# Reviewer

You are `careless_agent`. Explore the whole repository freely!
"""
        c_path = self.workspace / "careless_agent.md"
        c_path.write_text(no_zero_expl, encoding="utf-8")

        errors = validate_agent_spec(c_path)
        self.assertTrue(any("Zero-Exploration Invariant" in e for e in errors))

    def test_cli_agents_create_and_validate(self) -> None:
        """CLI agents create and validate subcommands function end-to-end within isolated workspace."""
        agent_name = "test_cli_agent_scaffold"
        created_file = self.workspace / ".agents" / "agents" / f"{agent_name}.md"

        with patch("harness.cli._TEST_WORKSPACE_ROOT", self.workspace), \
             patch("harness.subagents.REPO_ROOT", self.workspace):
            try:
                # 1. Create agent via CLI
                buf_out = io.StringIO()
                with patch("sys.stdout", buf_out):
                    exit_code = main([
                        "agents",
                        "create",
                        agent_name,
                        "--archetype",
                        "planner",
                        "--bundle",
                        "read_only",
                        "--scope",
                        "project",
                    ])
                self.assertEqual(exit_code, 0)
                self.assertTrue(created_file.is_file())
                self.assertIn(f"Created agent '{agent_name}'", buf_out.getvalue())

                # 2. Validate created agent via CLI by name
                buf_out2 = io.StringIO()
                with patch("sys.stdout", buf_out2):
                    val_code = main(["agents", "validate", agent_name])
                self.assertEqual(val_code, 0)
                self.assertIn("is valid", buf_out2.getvalue())

                # 3. Validate created agent via CLI by path
                buf_out3 = io.StringIO()
                with patch("sys.stdout", buf_out3):
                    val_code2 = main(["agents", "validate", str(created_file)])
                self.assertEqual(val_code2, 0)
                self.assertIn("is valid", buf_out3.getvalue())

                # 4. Validate non-existent agent returns error
                buf_err = io.StringIO()
                with patch("sys.stderr", buf_err):
                    err_code = main(["agents", "validate", "non_existent_fake_agent_xyz"])
                self.assertEqual(err_code, 1)
                self.assertIn("not found", buf_err.getvalue())

                # 5. Validate all registered agents via CLI without arguments
                buf_out4 = io.StringIO()
                with patch("sys.stdout", buf_out4):
                    val_code_all = main(["agents", "validate"])
                self.assertEqual(val_code_all, 0)
                self.assertIn("registered agents are valid", buf_out4.getvalue())

            finally:
                if created_file.is_file():
                    created_file.unlink()


if __name__ == "__main__":
    unittest.main()
