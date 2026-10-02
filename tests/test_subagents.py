#!/usr/bin/env python3
"""
Hermetic unit tests for PSL Specialist Subagents (harness/subagents.py).

Validates agent specification discovery, YAML frontmatter schemas,
archetype role mappings, toolgroup permission invariants, and sync operations.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from harness.subagents import (
    DEFAULT_AGENTS_DIR,
    DEFAULT_TARGET_DIR,
    AgentArchetype,
    AgentSpec,
    ToolPermissions,
    get_agent_spec,
    list_agent_specs,
    load_agent_spec,
    sync_agent_definitions,
)


class TestSpecialistSubagents(unittest.TestCase):
    """Test suite for specialist subagent definitions and registry operations."""

    WRITE_TOOLS = {"write_to_file", "replace_file_content"}
    EXEC_TOOLS = {"run_command", "manage_task"}

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.isolated_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_list_agents_discovers_all_archetypes(self) -> None:
        """Every specialist agent in harness/agents/ must be loaded and cataloged."""
        agents = list_agent_specs()
        self.assertEqual(len(agents), 3)

        archetypes = {a.archetype for a in agents}
        self.assertEqual(
            archetypes,
            {
                AgentArchetype.EXECUTIONER,
                AgentArchetype.HAMMER,
                AgentArchetype.AUDITOR,
            },
        )

    def test_agent_schema_contracts(self) -> None:
        """All agent specifications must satisfy required schema attributes."""
        agents = list_agent_specs()
        for agent in agents:
            with self.subTest(agent=agent.name):
                self.assertTrue(agent.name, "Agent name must not be empty")
                self.assertIsInstance(agent.archetype, AgentArchetype)
                self.assertTrue(agent.role, "Agent role must not be empty")
                self.assertTrue(agent.description, "Agent description must not be empty")
                self.assertGreater(
                    len(agent.description),
                    15,
                    f"Agent '{agent.name}' description too short",
                )
                self.assertTrue(
                    agent.system_prompt,
                    f"Agent '{agent.name}' must have a non-empty system prompt",
                )
                self.assertIsInstance(agent.permissions, ToolPermissions)
                self.assertIsInstance(agent.allowed_tools, list)
                self.assertGreater(
                    len(agent.allowed_tools),
                    0,
                    f"Agent '{agent.name}' must declare at least one allowed tool",
                )
                # Verify subagent recursion is disabled across all specialist agents
                self.assertFalse(
                    agent.can_subagent,
                    f"Specialist agent '{agent.name}' must not have subagent recursion enabled",
                )

    def test_builder_toolgroup_permissions(self) -> None:
        """Builder (Executioner) must have write tools, exec tools, and no subagents."""
        builder = get_agent_spec("harness_builder")
        self.assertIsNotNone(builder)
        self.assertEqual(builder.archetype, AgentArchetype.EXECUTIONER)
        self.assertTrue(builder.can_write, "Builder must have write permission")
        self.assertTrue(builder.can_execute, "Builder must have exec permission")
        self.assertFalse(builder.can_subagent, "Builder must not spawn subagents")

        # Must have write tools in allowed_tools
        tool_set = set(builder.allowed_tools)
        for wt in self.WRITE_TOOLS:
            self.assertIn(wt, tool_set, f"Builder must include write tool '{wt}'")
        for et in self.EXEC_TOOLS:
            self.assertIn(et, tool_set, f"Builder must include exec tool '{et}'")

    def test_reviewer_toolgroup_permissions(self) -> None:
        """Reviewer (Hammer) must be strictly read-only: no write tools, no exec tools."""
        reviewer = get_agent_spec("harness_reviewer")
        self.assertIsNotNone(reviewer)
        self.assertEqual(reviewer.archetype, AgentArchetype.HAMMER)
        self.assertFalse(reviewer.can_write, "Reviewer must not have write permission")
        self.assertFalse(reviewer.can_execute, "Reviewer must not have exec permission")
        self.assertFalse(reviewer.can_subagent, "Reviewer must not spawn subagents")

        # Must not contain any write or exec tools
        tool_set = set(reviewer.allowed_tools)
        for wt in self.WRITE_TOOLS:
            self.assertNotIn(
                wt, tool_set, f"Reviewer must NEVER include write tool '{wt}'"
            )
        for et in self.EXEC_TOOLS:
            self.assertNotIn(
                et, tool_set, f"Reviewer must NEVER include exec tool '{et}'"
            )

    def test_auditor_toolgroup_permissions(self) -> None:
        """Auditor (QA Verifier) must have exec tools to run tests, but zero write tools."""
        auditor = get_agent_spec("harness_auditor")
        self.assertIsNotNone(auditor)
        self.assertEqual(auditor.archetype, AgentArchetype.AUDITOR)
        self.assertFalse(auditor.can_write, "Auditor must not have write permission")
        self.assertTrue(auditor.can_execute, "Auditor must have exec permission")
        self.assertFalse(auditor.can_subagent, "Auditor must not spawn subagents")

        tool_set = set(auditor.allowed_tools)
        # Must have exec tools
        self.assertIn("run_command", tool_set)
        # Must NOT have write tools
        for wt in self.WRITE_TOOLS:
            self.assertNotIn(
                wt, tool_set, f"Auditor must NEVER include write tool '{wt}'"
            )

    def test_get_agent_spec_lookups_and_aliases(self) -> None:
        """get_agent_spec must resolve names, stems, and archetype aliases."""
        self.assertIsNotNone(get_agent_spec("harness_builder"))
        self.assertIsNotNone(get_agent_spec("harness-builder"))
        self.assertIsNotNone(get_agent_spec("builder"))
        self.assertIsNotNone(get_agent_spec("executioner"))

        self.assertIsNotNone(get_agent_spec("harness_reviewer"))
        self.assertIsNotNone(get_agent_spec("reviewer"))
        self.assertIsNotNone(get_agent_spec("hammer"))

        self.assertIsNotNone(get_agent_spec("harness_auditor"))
        self.assertIsNotNone(get_agent_spec("auditor"))
        self.assertIsNotNone(get_agent_spec("qa"))

        self.assertIsNone(get_agent_spec("unknown_agent_spec"))

    def test_archetype_from_string(self) -> None:
        """AgentArchetype.from_string resolves canonical names and aliases, rejects invalid."""
        self.assertEqual(
            AgentArchetype.from_string("executioner"), AgentArchetype.EXECUTIONER
        )
        self.assertEqual(
            AgentArchetype.from_string("builder"), AgentArchetype.EXECUTIONER
        )
        self.assertEqual(AgentArchetype.from_string("hammer"), AgentArchetype.HAMMER)
        self.assertEqual(AgentArchetype.from_string("reviewer"), AgentArchetype.HAMMER)
        self.assertEqual(AgentArchetype.from_string("auditor"), AgentArchetype.AUDITOR)
        self.assertEqual(
            AgentArchetype.from_string("qa_verifier"), AgentArchetype.AUDITOR
        )

        with self.assertRaises(ValueError):
            AgentArchetype.from_string("non_existent_archetype")

    def test_sync_agent_definitions_to_isolated_directory(self) -> None:
        """sync_agent_definitions correctly mirrors markdown files to destination."""
        target = self.isolated_path / "agents_target"
        synced = sync_agent_definitions(target_dir=target)

        self.assertEqual(len(synced), 3)
        for expected_file in [
            "harness_builder.md",
            "harness_reviewer.md",
            "harness_auditor.md",
        ]:
            dest = target / expected_file
            self.assertTrue(dest.exists(), f"Expected synced file {dest} not found")
            content = dest.read_text(encoding="utf-8")
            self.assertIn("archetype:", content)

    def test_agents_agents_mirror_in_sync(self) -> None:
        """The repository .agents/agents/ mirror must be in sync with harness/agents/."""
        source_specs = list_agent_specs(DEFAULT_AGENTS_DIR)
        for spec in source_specs:
            self.assertIsNotNone(spec.source_file)
            mirrored = DEFAULT_TARGET_DIR / spec.source_file.name
            self.assertTrue(
                mirrored.exists(),
                f"Mirrored agent definition missing at {mirrored}",
            )
            source_content = spec.source_file.read_text(encoding="utf-8")
            mirrored_content = mirrored.read_text(encoding="utf-8")
            self.assertEqual(
                source_content,
                mirrored_content,
                f"Mirrored agent at {mirrored} is out of sync with source {spec.source_file}",
            )


if __name__ == "__main__":
    unittest.main()
