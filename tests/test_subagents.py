#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Hermetic unit tests for PSL Specialist Subagents (harness/subagents.py).

Validates agent specification discovery, YAML frontmatter schemas,
archetype role mappings, toolgroup permission invariants, and sync operations.
"""

from __future__ import annotations

import json
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
    rehydrate_subagent_session,
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
        self.assertEqual(len(agents), 7)

        archetypes = {a.archetype for a in agents}
        self.assertEqual(
            archetypes,
            {
                AgentArchetype.EXECUTIONER,
                AgentArchetype.HAMMER,
                AgentArchetype.AUDITOR,
                AgentArchetype.PLANNER,
                AgentArchetype.COORDINATOR,
                AgentArchetype.MAIN,
                AgentArchetype.CUSTODIAN,
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
                self.assertTrue(
                    agent.inherit_customizations,
                    f"Agent '{agent.name}' must have inherit_customizations enabled",
                )
                if agent.archetype in (AgentArchetype.COORDINATOR, AgentArchetype.MAIN, AgentArchetype.PLANNER):
                    self.assertTrue(
                        agent.can_subagent,
                        f"Agent '{agent.name}' must have subagent permission enabled",
                    )
                else:
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
        self.assertTrue(
            auditor.permissions.enable_write_tools,
            "Auditor frontmatter must declare enable_write_tools: true",
        )
        self.assertFalse(auditor.can_subagent, "Auditor must not spawn subagents")

        tool_set = set(auditor.allowed_tools)
        # Must have exec tools
        self.assertIn("run_command", tool_set)
        # Must NOT have write tools
        for wt in self.WRITE_TOOLS:
            self.assertNotIn(
                wt, tool_set, f"Auditor must NEVER include write tool '{wt}'"
            )

    def test_custodian_toolgroup_permissions(self) -> None:
        """Custodian (Git Commit Gate) must have exec tools to run git, but zero write tools."""
        custodian = get_agent_spec("harness_custodian")
        self.assertIsNotNone(custodian)
        self.assertIsNotNone(get_agent_spec("custodian"))
        self.assertEqual(custodian.archetype, AgentArchetype.CUSTODIAN)
        self.assertFalse(custodian.can_write, "Custodian must not have write permission")
        self.assertTrue(custodian.can_execute, "Custodian must have exec permission")
        self.assertTrue(
            custodian.permissions.enable_write_tools,
            "Custodian frontmatter must declare enable_write_tools: true",
        )
        self.assertFalse(custodian.can_subagent, "Custodian must not spawn subagents")

        tool_set = set(custodian.allowed_tools)
        # Must have exec tools
        self.assertIn("run_command", tool_set)
        # Must NOT have write tools
        for wt in self.WRITE_TOOLS:
            self.assertNotIn(
                wt, tool_set, f"Custodian must NEVER include write tool '{wt}'"
            )

    def test_planner_toolgroup_permissions(self) -> None:
        """Planner must have read, write (artifact synthesis), subagent, and MCP enabled, but zero exec."""
        planner = get_agent_spec("planner")
        self.assertIsNotNone(planner)
        self.assertEqual(planner.archetype, AgentArchetype.PLANNER)
        self.assertTrue(planner.permissions.read)
        self.assertTrue(planner.can_write, "Planner must have write permission for artifact synthesis")
        self.assertFalse(planner.can_execute, "Planner must not have exec permission")
        self.assertTrue(planner.can_subagent, "Planner must have subagents enabled")
        self.assertTrue(planner.can_mcp, "Planner must have MCP access")

        tool_set = set(planner.allowed_tools)
        self.assertIn("write_to_file", tool_set)
        self.assertIn("ask_question", tool_set)
        self.assertIn("invoke_subagent", tool_set)
        self.assertIn("send_message", tool_set)
        self.assertIn("manage_subagents", tool_set)
        self.assertNotIn("run_command", tool_set)
        self.assertIn("view_file", tool_set)
        self.assertIn("manage_task", tool_set)

    def test_coordinator_toolgroup_permissions(self) -> None:
        """Coordinator must have read, write (artifact synthesis), and subagent permissions, but zero exec."""
        coord = get_agent_spec("coordinator")
        self.assertIsNotNone(coord)
        self.assertEqual(coord.archetype, AgentArchetype.COORDINATOR)
        self.assertTrue(coord.permissions.read)
        self.assertTrue(coord.can_write, "Coordinator must have write permission for artifact synthesis")
        self.assertFalse(coord.can_execute, "Coordinator must not have exec permission")
        self.assertTrue(coord.can_subagent, "Coordinator must have subagent permission")

        tool_set = set(coord.allowed_tools)
        self.assertIn("write_to_file", tool_set)
        self.assertNotIn("replace_file_content", tool_set)
        self.assertNotIn("run_command", tool_set)
        self.assertIn("invoke_subagent", tool_set)
        self.assertIn("send_message", tool_set)
        self.assertIn("manage_subagents", tool_set)
        self.assertIn("ask_question", tool_set)

    def test_psl_main_toolgroup_permissions(self) -> None:
        """Main agent (psl_main) must have full permissions across read, write, exec, subagent, mcp."""
        main_spec = get_agent_spec("psl_main")
        self.assertIsNotNone(main_spec)
        self.assertEqual(main_spec.archetype, AgentArchetype.MAIN)
        self.assertTrue(main_spec.can_write, "Main agent must have write permission")
        self.assertTrue(main_spec.can_execute, "Main agent must have exec permission")
        self.assertTrue(main_spec.can_subagent, "Main agent must have subagent permission")
        self.assertTrue(main_spec.can_mcp, "Main agent must have mcp permission")
        self.assertTrue(main_spec.permissions.enable_write_tools)
        self.assertTrue(main_spec.inherit_customizations)

        # Must include all write, exec, subagent tools, and full platform tools
        tool_set = set(main_spec.allowed_tools)
        for wt in self.WRITE_TOOLS:
            self.assertIn(wt, tool_set, f"Main agent must include write tool '{wt}'")
        for et in self.EXEC_TOOLS:
            self.assertIn(et, tool_set, f"Main agent must include exec tool '{et}'")
        self.assertIn("invoke_subagent", tool_set)
        self.assertNotIn("call_mcp_tool", tool_set, "MCP tools must not be listed statically in allowed_tools")
        self.assertEqual(len(main_spec.allowed_tools), 17)

    def test_get_agent_spec_lookups_and_aliases(self) -> None:
        """get_agent_spec must resolve names, stems, and archetype aliases."""
        self.assertIsNotNone(get_agent_spec("psl_main"))
        self.assertIsNotNone(get_agent_spec("psl-main"))
        self.assertIsNotNone(get_agent_spec("main"))
        self.assertIsNotNone(get_agent_spec("lead"))
        self.assertIsNotNone(get_agent_spec("general"))
        self.assertIsNotNone(get_agent_spec("default"))

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

        self.assertIsNotNone(get_agent_spec("planner"))
        self.assertIsNotNone(get_agent_spec("architect"))

        self.assertIsNotNone(get_agent_spec("coordinator"))
        self.assertIsNotNone(get_agent_spec("orchestrator"))

        self.assertIsNotNone(get_agent_spec("harness_custodian"))
        self.assertIsNotNone(get_agent_spec("custodian"))

        self.assertIsNone(get_agent_spec("unknown_agent_spec"))

    def test_archetype_from_string(self) -> None:
        """AgentArchetype.from_string resolves canonical names and aliases, rejects invalid."""
        self.assertEqual(AgentArchetype.from_string("main"), AgentArchetype.MAIN)
        self.assertEqual(AgentArchetype.from_string("psl_main"), AgentArchetype.MAIN)
        self.assertEqual(AgentArchetype.from_string("lead"), AgentArchetype.MAIN)
        self.assertEqual(AgentArchetype.from_string("general"), AgentArchetype.MAIN)
        self.assertEqual(AgentArchetype.from_string("default"), AgentArchetype.MAIN)

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
        self.assertEqual(AgentArchetype.from_string("planner"), AgentArchetype.PLANNER)
        self.assertEqual(AgentArchetype.from_string("architect"), AgentArchetype.PLANNER)
        self.assertEqual(AgentArchetype.from_string("coordinator"), AgentArchetype.COORDINATOR)
        self.assertEqual(AgentArchetype.from_string("orchestrator"), AgentArchetype.COORDINATOR)
        self.assertEqual(AgentArchetype.from_string("custodian"), AgentArchetype.CUSTODIAN)
        self.assertEqual(AgentArchetype.from_string("harness_custodian"), AgentArchetype.CUSTODIAN)
        self.assertEqual(AgentArchetype.from_string("git_custodian"), AgentArchetype.CUSTODIAN)
        self.assertEqual(AgentArchetype.from_string("commit_gate"), AgentArchetype.CUSTODIAN)
        self.assertEqual(AgentArchetype.from_string("subagent_x_custodian"), AgentArchetype.CUSTODIAN)

        with self.assertRaises(ValueError):
            AgentArchetype.from_string("non_existent_archetype")

    def test_sync_agent_definitions_to_isolated_directory(self) -> None:
        """sync_agent_definitions correctly mirrors markdown files to destination."""
        target = self.isolated_path / "agents_target"
        synced = sync_agent_definitions(target_dir=target)

        self.assertEqual(len(synced), 7)
        for expected_file in [
            "harness_builder.md",
            "harness_reviewer.md",
            "harness_auditor.md",
            "planner.md",
            "coordinator.md",
            "psl_main.md",
            "harness_custodian.md",
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

    def test_zero_exploration_invariant_in_prompts(self) -> None:
        """All specialist subagent system prompts must enforce Zero-Exploration or Targeted Macro Sweep Invariant."""
        specs = list_agent_specs()
        self.assertGreaterEqual(len(specs), 6)
        for agent in specs:
            with self.subTest(agent=agent.name):
                has_inv = (
                    "Zero-Exploration Invariant" in agent.system_prompt
                    or "Targeted Macro & Deduplication Sweep Invariant" in agent.system_prompt
                )
                self.assertTrue(
                    has_inv,
                    f"Agent {agent.name} missing exploration invariant in prompt",
                )
                self.assertIn(
                    "list_dir",
                    agent.system_prompt,
                    f"Agent {agent.name} prompt must explicitly mention list_dir",
                )
                self.assertIn(
                    "find_by_name",
                    agent.system_prompt,
                    f"Agent {agent.name} prompt must explicitly mention find_by_name",
                )

    def test_sync_agent_definitions_with_filter_and_dedup(self) -> None:
        """sync_agent_definitions supports agent_names filtering, dedup, and override."""
        target = self.isolated_path / "filtered_agents"

        # 1. Sync specific agent
        synced = sync_agent_definitions(target_dir=target, agent_names=["executioner"])
        self.assertEqual(len(synced), 1)
        self.assertEqual(synced[0].name, "harness_builder.md")

        # 2. Dedup skips identical file
        synced_dedup = sync_agent_definitions(target_dir=target, agent_names=["executioner"], dedup=True)
        self.assertEqual(len(synced_dedup), 0)

        # 3. Override reinstalls file
        synced_override = sync_agent_definitions(target_dir=target, agent_names=["executioner"], override=True)
        self.assertEqual(len(synced_override), 1)

    def test_rehydrate_subagent_session_completed(self) -> None:
        """rehydrate_subagent_session correctly detects completed session and extracts deltas."""
        conv_dir = self.isolated_path / "conv-completed-123"
        log_dir = conv_dir / ".system_generated" / "logs"
        log_dir.mkdir(parents=True)
        t_file = log_dir / "transcript.jsonl"

        lines = [
            json.dumps({
                "step_index": 1,
                "type": "USER_INPUT",
                "content": "You are `harness_builder` (executioner).\n<USER_REQUEST>Implement feature X in harness/core.py</USER_REQUEST>",
            }),
            json.dumps({
                "step_index": 2,
                "type": "MODEL_TURN",
                "tool_calls": [
                    {
                        "name": "replace_file_content",
                        "args": {
                            "TargetFile": "/path/to/harness/core.py",
                            "TargetContent": "old_code()",
                            "ReplacementContent": "new_code()",
                        },
                    }
                ],
            }),
            json.dumps({
                "step_index": 3,
                "type": "MODEL_TURN",
                "content": "Execution complete. All tasks passed.",
                "tool_calls": [
                    {
                        "name": "send_message",
                        "args": {"Recipient": "parent", "Message": "Done"},
                    }
                ],
                "status": "COMPLETED",
            }),
        ]
        t_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        res = rehydrate_subagent_session("conv-completed-123", brain_dir=self.isolated_path)

        self.assertEqual(res["status"], "REHYDRATED_COMPLETED")
        self.assertIn("builder", res["role"].lower())
        self.assertIn("Implement feature X", res["prompt"])
        self.assertIn("/path/to/harness/core.py", res["completed_files"])
        self.assertGreater(len(res["diffs"]), 0)
        self.assertEqual(res["last_step"], 3)
        self.assertEqual(res["step_count"], 3)
        self.assertEqual(res["tool_calls_count"], 2)
        self.assertEqual(res["error"], "")

    def test_rehydrate_subagent_session_interrupted(self) -> None:
        """rehydrate_subagent_session detects abruptly terminated / interrupted subagents."""
        conv_dir = self.isolated_path / "conv-interrupted-456"
        log_dir = conv_dir / ".system_generated" / "logs"
        log_dir.mkdir(parents=True)
        t_file = log_dir / "transcript.jsonl"

        lines = [
            json.dumps({
                "step_index": 1,
                "type": "USER_INPUT",
                "content": "You are `harness_builder`.\n<USER_REQUEST>Refactor worker</USER_REQUEST>",
            }),
            json.dumps({
                "step_index": 2,
                "type": "MODEL_TURN",
                "tool_calls": [
                    {
                        "name": "run_command",
                        "args": {"CommandLine": "python3 worker.py"},
                    }
                ],
                "status": "INTERRUPTED",
            }),
        ]
        t_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        res = rehydrate_subagent_session("conv-interrupted-456", brain_dir=self.isolated_path)
        self.assertEqual(res["status"], "REHYDRATED_INTERRUPTED")
        self.assertEqual(res["last_step"], 2)
        self.assertEqual(res["step_count"], 2)

    def test_rehydrate_subagent_session_failed(self) -> None:
        """rehydrate_subagent_session detects fatal crash / failed subagent session."""
        conv_dir = self.isolated_path / "conv-failed-789"
        log_dir = conv_dir / ".system_generated" / "logs"
        log_dir.mkdir(parents=True)
        t_file = log_dir / "transcript.jsonl"

        lines = [
            json.dumps({
                "step_index": 1,
                "type": "USER_INPUT",
                "content": "You are `harness_auditor`.\n<USER_REQUEST>Audit suite</USER_REQUEST>",
            }),
            json.dumps({
                "step_index": 2,
                "type": "MODEL_TURN",
                "status": "FAILED",
                "error": "SyntaxError: invalid syntax",
                "content": "Traceback (most recent call last):\n  File 'test.py', line 12",
            }),
        ]
        t_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        res = rehydrate_subagent_session("conv-failed-789", brain_dir=self.isolated_path)
        self.assertEqual(res["status"], "REHYDRATED_FAILED")
        self.assertIn("SyntaxError", res["error"])
        self.assertEqual(res["last_step"], 2)

    def test_rehydrate_subagent_not_found(self) -> None:
        """rehydrate_subagent_session raises FileNotFoundError for missing sessions."""
        with self.assertRaises(FileNotFoundError):
            rehydrate_subagent_session("non-existent-session-id", brain_dir=self.isolated_path)

    def test_cli_agents_rehydrate_command(self) -> None:
        """CLI invocation 'psl agents rehydrate --id <id> --json' executes cleanly."""
        from unittest.mock import patch
        import io
        from harness.cli import main as cli_main

        conv_dir = self.isolated_path / "conv-cli-test"
        log_dir = conv_dir / ".system_generated" / "logs"
        log_dir.mkdir(parents=True)
        t_file = log_dir / "transcript.jsonl"
        t_file.write_text(
            json.dumps({
                "step_index": 1,
                "type": "USER_INPUT",
                "content": "You are `harness_builder`.\n<USER_REQUEST>CLI rehydrate test</USER_REQUEST>",
                "status": "COMPLETED",
            }) + "\n",
            encoding="utf-8",
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cli_main([
                "agents",
                "rehydrate",
                "--id",
                "conv-cli-test",
                "--brain-dir",
                str(self.isolated_path),
                "--json",
            ])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue())
            self.assertEqual(data["conversation_id"], "conv-cli-test")
            self.assertEqual(data["status"], "REHYDRATED_COMPLETED")


if __name__ == "__main__":
    unittest.main()


