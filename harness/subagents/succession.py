# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Harness: Horizontal Succession Protocol & Self-Alias Ladder (ADR-031 / Issue #77).

Implements:
1. Dynamic Self-Alias Ladder for invoke_subagent(TypeName='self', Workspace='inherit').
2. Standardized 6-section Succession Prompt Blueprint for generation handoff.
3. Structured Subagent Custody Transfer protocol.
4. Successor generation directory scaffolding.
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

ARCHETYPE_ALIAS_MAP: Dict[str, str] = {
    # Coordinator aliases
    "self": "agyis_coordinator",
    "coordinator": "agyis_coordinator",
    "agyis_coordinator": "agyis_coordinator",
    "flight_director": "agyis_coordinator",
    "cockpit_director": "agyis_coordinator",
    # Architect aliases
    "architect": "agyis_architect",
    "agyis_architect": "agyis_architect",
    # Swarm orchestrator
    "swarm_orchestrator": "swarm_orchestrator",
    "agyis_swarm_orchestrator": "swarm_orchestrator",
    # Builder aliases
    "builder": "agyis_builder",
    "agyis_builder": "agyis_builder",
    "deep_execution": "agyis_builder",
    "executioner": "agyis_builder",
    # Reviewer aliases
    "reviewer": "agyis_reviewer",
    "agyis_reviewer": "agyis_reviewer",
    # Custodian aliases
    "custodian": "agyis_custodian",
    "agyis_custodian": "agyis_custodian",
    # Auditor aliases
    "auditor": "agyis_auditor",
    "agyis_auditor": "agyis_auditor",
}

DEFAULT_ARCHETYPE: str = "agyis_coordinator"


def resolve_self_alias(role_str: Optional[str] = None) -> str:
    """
    Resolves the dynamic alias ladder for `invoke_subagent(TypeName='self', Workspace='inherit')`.
    If `role_str` is 'self' (case-insensitive) or empty/None:
    Looks up active role from AGYIS_ROLE or GEMINI_ROLE environment variables.
    Normalizes string and maps to registered specialist archetype.
    """
    target = role_str
    if not target or not isinstance(target, str) or target.strip().lower() == "self":
        target = os.environ.get("AGYIS_ROLE") or os.environ.get("GEMINI_ROLE") or DEFAULT_ARCHETYPE

    norm = target.strip().lower().replace("-", "_")
    return ARCHETYPE_ALIAS_MAP.get(norm, DEFAULT_ARCHETYPE)


def build_succession_prompt(
    current_gen: int,
    next_gen: int,
    session_id: str,
    tokens: int,
    plan_path: Optional[str] = None,
    next_task: Optional[str] = None,
    project_name: str = "Agyis Harness",
    active_subagents: Optional[List[Any]] = None,
) -> str:
    """
    Generates standardized succession prompt blueprint matching §3.4 of ADR-031 design spec.
    Enforces the 6 mandatory succession boot directives:
    1. Read pre-compaction state checkpoint: view_file('.agents/artifacts/compaction_checkpoint_latest.md').
    2. Verify repo integrity: git status. Strict AC4 Work Preservation Contract.
    3. Inspect active plan: plan_path.
    4. Assume custody of active background subagents.
    5. Immediately resume current phase starting at next_task.
    6. Autonomous Continuation: zero operator re-prompting.
    """
    resolved_plan = plan_path or ".agents/artifacts/implementation_plan.md"
    resolved_task = next_task or "Continue active milestone execution"

    subagents_note = ""
    if active_subagents:
        subagents_note = (
            f"\n- **In-Flight Subagents ({len(active_subagents)})**: Custody transfer records attached in checkpoint.\n"
            "  * Retain conversation IDs for HEALTHY/AMBER subagents.\n"
            "  * Retire RED_ALERT subagents and respawn successors."
        )

    return f"""<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Agyis Horizontal Succession Directive: Generation {current_gen} -> Generation {next_gen} -->

# 🚀 Generation {next_gen} Succession Hand-Off ({project_name})

You are the Generation {next_gen} successor orchestrator spawned to continue autonomous engineering execution.
Your predecessor (Generation {current_gen}, Session `{session_id}`) transferred authority after reaching `{tokens:,}` tokens.

---

## 🛠️ Mandatory 6-Step Succession Boot Sequence

You MUST execute the following sequence immediately upon awakening without pause or human prompting:

1. [ ] **Read Pre-Compaction Checkpoint**:
   Call `view_file('.agents/artifacts/compaction_checkpoint_latest.md')` to restore complete situational awareness, active phase, subagent roster, and git diff.

2. [ ] **Verify Repository Integrity (AC4 Work Preservation Contract)**:
   Run `git status` and `git diff --stat`.
   > [!IMPORTANT]
   > In-flight modifications represent intentional partial work.
   > Strictly prohibit destructive resets: NEVER run `git checkout -- .`, `git reset --hard`, or `git clean -fd`.

3. [ ] **Inspect Active Implementation Plan**:
   Call `view_file('{resolved_plan}')` to verify task completion status and remaining phases.

4. [ ] **Assume Subagent Custody**:
   Adopt conversation IDs for active subagents listed in Section 4 of the checkpoint.{subagents_note}

5. [ ] **Resume Active Phase Immediately**:
   Resume active milestone work starting at:
   > `{resolved_task}`

6. [ ] **Autonomous Continuation (Zero Operator Re-prompting)**:
   Do NOT ask the operator *"What was I doing?"* or *"Should I continue?"*.
   Proceed directly with implementation!
"""


def build_custody_transfer_payload(
    predecessor_id: str,
    successor_id: str,
    subagents: List[Any],
) -> Dict[str, Any]:
    """
    Returns structured custody transfer payload recording handoff from predecessor to successor.
    """
    iso_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entries: List[Dict[str, Any]] = []

    for s in subagents:
        cid = getattr(s, "conversation_id", None) or (s.get("conversation_id") if isinstance(s, dict) else str(s))
        role = getattr(s, "role", None) or (s.get("role") if isinstance(s, dict) else "subagent")
        step_count = getattr(s, "step_count", 0) if hasattr(s, "step_count") else (s.get("step_count", 0) if isinstance(s, dict) else 0)
        token_count = getattr(s, "token_count", 0) if hasattr(s, "token_count") else (s.get("token_count", 0) if isinstance(s, dict) else 0)
        health_zone = getattr(s, "health_zone", "HEALTHY") if hasattr(s, "health_zone") else (s.get("health_zone", "HEALTHY") if isinstance(s, dict) else "HEALTHY")
        recommendation = getattr(s, "recommendation", "REUSE") if hasattr(s, "recommendation") else (s.get("recommendation", "REUSE") if isinstance(s, dict) else "REUSE")

        entries.append({
            "conversation_id": cid,
            "role": role,
            "step_count": step_count,
            "token_count": token_count,
            "health_zone": health_zone,
            "recommendation": recommendation,
        })

    return {
        "timestamp": iso_time,
        "predecessor_id": predecessor_id,
        "successor_id": successor_id,
        "active_subagents_count": len(entries),
        "entries": entries,
        "instructions": [
            "Retain conversation IDs for subagents marked HEALTHY or AMBER.",
            "Send status ping / custody claim via send_message(Recipient='<conv_id>') if awaiting direction.",
            "Retire subagents marked RED_ALERT (>80k tokens) by spawning fresh successors.",
        ],
    }


def scaffold_successor_generation(
    workspace_dir: Union[Path, str],
    orchestrator_role: str = "agyis_coordinator",
    next_gen: int = 2,
) -> Path:
    """
    Scaffolds `.agents/teamwork/<orchestrator>_gen<next_gen>/` directory.
    Creates directory on disk and returns its Path.
    """
    ws = Path(workspace_dir)
    target_dir = ws / ".agents" / "teamwork" / f"{orchestrator_role}_gen{next_gen}"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir
