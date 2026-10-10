# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Specialist subagents CLI commands (ADR-014).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional

from harness.subagents import (
    DEFAULT_AGENTS_DIR,
    REPO_ROOT,
    AgentArchetype,
    CAPABILITY_BUNDLES,
    get_agent_spec,
    inspect_workspace_context,
    list_agent_specs,
    scaffold_agent_markdown,
    sync_agent_definitions,
    validate_agent_spec,
)


def _get_repo_root() -> Path:
    import harness.cli
    import harness.subagents
    return (
        getattr(harness.cli, "REPO_ROOT", None)
        or getattr(harness.subagents, "REPO_ROOT", None)
        or REPO_ROOT
    )


def cmd_agents(args: argparse.Namespace) -> int:
    """Lists, inspects, creates, validates, or synchronizes specialist subagents."""
    action_or_name = getattr(args, "name", None)
    target_name = getattr(args, "target_name", None)

    # 0. agents rehydrate [--id <conv_id>] [--recent-hours <N>]
    if action_or_name == "rehydrate":
        from harness.subagents import list_active_subagent_statuses, rehydrate_subagent_session

        conv_id = getattr(args, "id", None) or target_name
        brain_dir = getattr(args, "brain_dir", None)

        if not conv_id:
            statuses = list_active_subagent_statuses(brain_dir=brain_dir)
            if not statuses:
                sys.stderr.write("No active subagent sessions found to rehydrate.\n")
                return 1
            conv_id = statuses[0].conversation_id

        try:
            res = rehydrate_subagent_session(conv_id=conv_id, brain_dir=brain_dir)
        except FileNotFoundError as exc:
            sys.stderr.write(f"Error: {exc}\n")
            return 1

        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
            return 0

        print(f"Rehydrated Subagent Session: {res['conversation_id']}")
        print(f"  Role:            {res['role']}")
        print(f"  Status:          {res['status']}")
        print(f"  Step Count:      {res['step_count']}")
        print(f"  Tool Calls:      {res['tool_calls_count']}")
        print(f"  Last Step:       {res['last_step_index']}")
        if res.get("completed_files"):
            print(f"  Completed Files ({len(res['completed_files'])}):")
            for cf in res["completed_files"]:
                print(f"    • {cf}")
        if res.get("error"):
            print(f"  Error:           {res['error']}")
        if res.get("prompt"):
            prompt_preview = res["prompt"][:150].replace("\n", " ")
            print(f"  Prompt:          {prompt_preview}...")
        return 0

    # 1. agents create <name>
    if action_or_name == "create":
        name = target_name
        if not name:
            if sys.stdin.isatty():
                try:
                    name = input("Enter agent name: ").strip()
                except (EOFError, KeyboardInterrupt):
                    sys.stderr.write("\nAborted.\n")
                    return 1
            if not name:
                sys.stderr.write("Error: Agent name is required for create.\n")
                return 1

        name = name.strip().lower().replace(" ", "_")
        arch_str = getattr(args, "archetype", None)
        if not arch_str:
            if sys.stdin.isatty():
                print("Available archetypes:")
                print("  1) main         (Lead Architect & Master Implementer)")
                print("  2) executioner  (Worker / Implementer)")
                print("  3) hammer       (Ruthless Reviewer)")
                print("  4) auditor      (QA Verifier)")
                print("  5) planner      (Architect / Planner)")
                print("  6) coordinator  (Swarm Coordinator)")
                try:
                    choice = input("Select archetype [1-6 or name] (default: executioner): ").strip()
                except (EOFError, KeyboardInterrupt):
                    sys.stderr.write("\nAborted.\n")
                    return 1
                mapping = {
                    "1": "main",
                    "2": "executioner",
                    "3": "hammer",
                    "4": "auditor",
                    "5": "planner",
                    "6": "coordinator",
                }
                arch_str = mapping.get(choice, choice) or "executioner"
            else:
                arch_str = "executioner"

        try:
            archetype = AgentArchetype.from_string(arch_str)
        except ValueError as exc:
            sys.stderr.write(f"Error: {exc}\n")
            return 1

        bundle_str = getattr(args, "bundle", None)
        if not bundle_str:
            if sys.stdin.isatty():
                print("Available capability bundles:")
                print("  1) read_only    (view_file, list_dir, grep_search, find_by_name, read_url, search_web)")
                print("  2) verifier     (read_only + run_command, manage_task)")
                print("  3) builder      (verifier + write_to_file, replace_file_content)")
                print("  4) orchestrator (read_only + invoke_subagent, send_message, manage_subagents, manage_task)")
                print("  5) full         (all platform tools enabled)")
                try:
                    choice = input("Select capability bundle [1-5 or name] (default: auto): ").strip()
                except (EOFError, KeyboardInterrupt):
                    sys.stderr.write("\nAborted.\n")
                    return 1
                b_map = {
                    "1": "read_only",
                    "2": "verifier",
                    "3": "builder",
                    "4": "orchestrator",
                    "5": "full",
                }
                bundle_str = b_map.get(choice, choice) or None

        scope = getattr(args, "scope", "project") or "project"
        if scope == "global":
            target_dir = Path.home() / ".gemini" / "config" / "agents"
        else:
            target_dir = _get_repo_root() / ".agents" / "agents"

        model = getattr(args, "model", "inherit") or "inherit"
        ws_ctx = inspect_workspace_context()
        content = scaffold_agent_markdown(
            name=name,
            archetype=archetype,
            bundle=bundle_str,
            model=model,
            workspace_context=ws_ctx,
        )

        target_dir.mkdir(parents=True, exist_ok=True)
        out_path = target_dir / f"{name}.md"
        out_path.write_text(content, encoding="utf-8")

        val_errors = validate_agent_spec(out_path)
        if val_errors:
            for e in val_errors:
                sys.stderr.write(f"Warning: {e}\n")

        print(f"✔ Created agent '{name}' ({archetype.value}) at {out_path}")
        return 0

    # 2. agents validate <path_or_name>
    if action_or_name == "validate":
        target = target_name
        if not target:
            sys.stderr.write("Error: Path or agent name required for validate.\n")
            return 1

        cand = Path(target)
        found_file: Optional[Path] = None
        if cand.is_file():
            found_file = cand
        else:
            for check_dir in (_get_repo_root() / ".agents" / "agents", DEFAULT_AGENTS_DIR):
                p1 = check_dir / f"{target}.md"
                p2 = check_dir / target
                if p1.is_file():
                    found_file = p1
                    break
                elif p2.is_file():
                    found_file = p2
                    break
            if not found_file:
                spec = get_agent_spec(target)
                if spec and spec.source_file and spec.source_file.is_file():
                    found_file = spec.source_file

        if not found_file:
            sys.stderr.write(f"Error: Agent file '{target}' not found.\n")
            return 1

        errors = validate_agent_spec(found_file)
        if not errors:
            print(f"✔ Agent '{found_file.name}' is valid.")
            return 0
        else:
            sys.stderr.write(f"✘ Agent '{found_file.name}' failed validation with {len(errors)} error(s):\n")
            for err in errors:
                sys.stderr.write(f"  • {err}\n")
            return 1

    # 3. agents --sync
    if getattr(args, "sync", False):
        synced = sync_agent_definitions(target_dir=_get_repo_root() / ".agents" / "agents")
        print(f"✔ Synchronized {len(synced)} agent definitions to .agents/agents/:")
        for p in synced:
            print(f"  • {p.name} -> {p}")
        return 0

    # 4. agents <name> (inspect)
    if action_or_name:
        spec = get_agent_spec(action_or_name)
        if not spec:
            sys.stderr.write(f"Error: Agent '{action_or_name}' not found.\n")
            return 1
        if getattr(args, "json", False):
            print(
                json.dumps(
                    {
                        "name": spec.name,
                        "archetype": spec.archetype.value,
                        "role": spec.role,
                        "description": spec.description,
                        "permissions": {
                            "read": spec.permissions.read,
                            "write": spec.permissions.write,
                            "execute": spec.permissions.execute,
                            "subagent": spec.permissions.subagent,
                            "mcp": spec.permissions.mcp,
                        },
                        "allowed_tools": spec.allowed_tools,
                        "source_file": str(spec.source_file) if spec.source_file else None,
                    },
                    indent=2,
                )
            )
            return 0
        print(f"Agent:       {spec.name}")
        print(f"Archetype:   {spec.archetype.value}")
        print(f"Role:        {spec.role}")
        print(
            f"Permissions: write={spec.can_write}, exec={spec.can_execute}, subagent={spec.can_subagent}"
        )
        print(f"Allowed Tools ({len(spec.allowed_tools)}): {', '.join(spec.allowed_tools)}")
        print(f"Description:\n  {spec.description}\n")
        print("=" * 60)
        print(spec.system_prompt)
        return 0

    agents = list_agent_specs()
    if getattr(args, "json", False):
        print(
            json.dumps(
                [
                    {
                        "name": a.name,
                        "archetype": a.archetype.value,
                        "role": a.role,
                        "description": a.description,
                        "can_write": a.can_write,
                        "can_execute": a.can_execute,
                        "tools_count": len(a.allowed_tools),
                    }
                    for a in agents
                ],
                indent=2,
            )
        )
        return 0

    print(f"PSL Specialist Subagents ({len(agents)} registered):")
    print("-" * 60)
    for a in agents:
        caps = []
        if a.can_write:
            caps.append("write")
        else:
            caps.append("read-only")
        if a.can_execute:
            caps.append("exec")
        if a.can_subagent:
            caps.append("subagent")
        cap_str = f"[{' | '.join(caps)}]"
        print(f"  • {a.name:<18} ({a.role}) {cap_str}")
        print(f"    {a.description}")
        print(f"    Tools ({len(a.allowed_tools)}): {', '.join(a.allowed_tools)}")
    print()
    return 0
