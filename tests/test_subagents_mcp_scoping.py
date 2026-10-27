#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Unit Tests for Specialist Subagent Dynamic MCP Tool Scoping (Issue #97).

Validates:
1. ToolPermissions boolean and list scoping (can_mcp, allowed_mcp_servers).
2. AgentSpec properties reflection for MCP permissions.
3. Frontmatter serialization in scaffold_agent_markdown().
4. Validation of non-empty strings in validator.py.
5. agyis_investigator specification has can_mcp == True.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from harness.subagents.spec import (
    AgentArchetype,
    AgentSpec,
    ToolPermissions,
    load_agent_spec,
)
from harness.subagents.scaffold import scaffold_agent_markdown
from harness.subagents.validator import validate_agent_spec


class TestSubagentsMCPScoping(unittest.TestCase):
    """Hermetic unit tests for subagent MCP permissions & scoping contracts (<0.05s SLA)."""

    def test_tool_permissions_boolean_false(self):
        """ToolPermissions with default or explicit False has can_mcp False and empty servers."""
        perms_default = ToolPermissions()
        self.assertFalse(perms_default.can_mcp)
        self.assertEqual(perms_default.allowed_mcp_servers, ())

        perms_dict = ToolPermissions.from_dict({"mcp": False})
        self.assertFalse(perms_dict.can_mcp)
        self.assertEqual(perms_dict.allowed_mcp_servers, ())

    def test_tool_permissions_boolean_true(self):
        """ToolPermissions with True has can_mcp True and unrestricted empty servers tuple."""
        perms = ToolPermissions(mcp=True)
        self.assertTrue(perms.can_mcp)
        self.assertEqual(perms.allowed_mcp_servers, ())

        perms_from_dict = ToolPermissions.from_dict({"mcp": True})
        self.assertTrue(perms_from_dict.can_mcp)
        self.assertEqual(perms_from_dict.allowed_mcp_servers, ())

        perms_str_true = ToolPermissions.from_dict({"mcp": "true"})
        self.assertTrue(perms_str_true.can_mcp)
        self.assertEqual(perms_str_true.allowed_mcp_servers, ())

    def test_tool_permissions_list_scoping(self):
        """ToolPermissions with list of server names scopes allowed_mcp_servers."""
        perms = ToolPermissions.from_dict({"mcp": ["rea", "chrome-devtools", " " ]})
        self.assertTrue(perms.can_mcp)
        self.assertEqual(perms.allowed_mcp_servers, ("rea", "chrome-devtools"))

    def test_tool_permissions_mcp_servers_field(self):
        """ToolPermissions with mcp_servers list or tuple correctly scopes allowed_mcp_servers."""
        perms = ToolPermissions.from_dict({"mcp_servers": ["postgres", "rea"]})
        self.assertTrue(perms.can_mcp)
        self.assertEqual(perms.allowed_mcp_servers, ("postgres", "rea"))

    def test_agent_spec_can_mcp_and_allowed_servers_delegation(self):
        """AgentSpec exposes can_mcp and allowed_mcp_servers from permissions."""
        perms = ToolPermissions.from_dict({"mcp": ["rea"]})
        spec = AgentSpec(
            name="test_worker",
            archetype=AgentArchetype.EXECUTIONER,
            description="Test worker",
            role="Worker",
            system_prompt="Test prompt",
            permissions=perms,
        )
        self.assertTrue(spec.can_mcp)
        self.assertEqual(spec.allowed_mcp_servers, ("rea",))

    def test_scaffold_markdown_serialization_boolean(self):
        """Scaffolding serializes boolean mcp correctly."""
        # Unrestricted true
        md_true = scaffold_agent_markdown(
            name="test_planner",
            archetype=AgentArchetype.PLANNER,
            permissions={"mcp": True},
        )
        self.assertIn("mcp: true", md_true)

        # False
        md_false = scaffold_agent_markdown(
            name="test_worker",
            archetype=AgentArchetype.EXECUTIONER,
            permissions={"mcp": False},
        )
        self.assertIn("mcp: false", md_false)

    def test_scaffold_markdown_serialization_list(self):
        """Scaffolding serializes list mcp servers cleanly in YAML."""
        md_scoped = scaffold_agent_markdown(
            name="test_builder",
            archetype=AgentArchetype.EXECUTIONER,
            permissions={"mcp": ["rea", "chrome-devtools"]},
        )
        self.assertIn("mcp:\n    - rea\n    - chrome-devtools", md_scoped)

    def test_validator_rejects_empty_or_non_string_server_entries(self):
        """Validator flags invalid non-string or empty entries in mcp / mcp_servers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_spec_path = Path(tmpdir) / "bad_agent.md"
            bad_content = """---
name: bad_agent
archetype: executioner
description: Bad agent
role: Executioner
subagent: true
mainAgent: true
permissions:
  read: true
  write: true
  execute: true
  subagents: false
  mcp:
    - "rea"
    - ""
tools:
  - view_file
  - run_command
---
# Prompt
Zero-Exploration Invariant requires list_dir and find_by_name.
"""
            bad_spec_path.write_text(bad_content, encoding="utf-8")
            errors = validate_agent_spec(bad_spec_path)
            self.assertTrue(any("Invalid entry in permissions.mcp" in e for e in errors))

    def test_validator_accepts_valid_scoped_mcp(self):
        """Validator accepts properly formatted list of MCP servers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = Path(tmpdir) / "good_agent.md"
            content = """---
name: good_agent
archetype: executioner
description: Good agent
role: Executioner
subagent: true
mainAgent: true
permissions:
  read: true
  write: true
  execute: true
  subagents: false
  mcp:
    - rea
    - chrome-devtools
tools:
  - view_file
  - run_command
---
# Prompt
Zero-Exploration Invariant requires list_dir and find_by_name.
"""
            spec_path.write_text(content, encoding="utf-8")
            errors = validate_agent_spec(spec_path)
            self.assertEqual(errors, [])

    def test_agyis_investigator_spec_has_mcp_enabled(self):
        """agyis_investigator agent definition has mcp enabled."""
        repo_root = Path(__file__).resolve().parent.parent
        spec_path = repo_root / "harness" / "agents" / "agyis_investigator.md"
        self.assertTrue(spec_path.is_file(), f"Missing {spec_path}")
        spec = load_agent_spec(spec_path)
        self.assertTrue(spec.can_mcp)
        self.assertEqual(spec.allowed_mcp_servers, ())
        self.assertIn("Read-only MCP diagnostic", spec.system_prompt)


if __name__ == "__main__":
    unittest.main()
