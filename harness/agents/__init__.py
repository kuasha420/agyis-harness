# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Specialist agent definitions and legacy alias bridge (ADR-014, Phase 3).

Transparently maps legacy agent names (harness_builder, harness_reviewer,
harness_custodian, harness_auditor, coordinator, planner, psl_main)
to the canonical unified agyis_* definitions.
"""

from __future__ import annotations

from typing import Dict

# Legacy name / alias -> canonical agyis_* agent definition name
LEGACY_AGENT_ALIASES: Dict[str, str] = {
    # Builder / Executioner
    "harness_builder": "agyis_builder",
    "harness-builder": "agyis_builder",
    "builder": "agyis_builder",
    "executioner": "agyis_builder",
    "worker": "agyis_builder",
    "implementer": "agyis_builder",
    # Reviewer / Hammer
    "harness_reviewer": "agyis_reviewer",
    "harness-reviewer": "agyis_reviewer",
    "reviewer": "agyis_reviewer",
    "hammer": "agyis_reviewer",
    "inspector": "agyis_reviewer",
    # Custodian / Git Commit Gate
    "harness_custodian": "agyis_custodian",
    "harness-custodian": "agyis_custodian",
    "custodian": "agyis_custodian",
    "git_custodian": "agyis_custodian",
    "commit_gate": "agyis_custodian",
    "subagent_x_custodian": "agyis_custodian",
    # Auditor / Verifier
    "harness_auditor": "agyis_auditor",
    "harness-auditor": "agyis_auditor",
    "auditor": "agyis_auditor",
    "qa": "agyis_auditor",
    "qa_verifier": "agyis_auditor",
    "verifier": "agyis_auditor",
    # Coordinator
    "coordinator": "agyis_coordinator",
    "orchestrator": "agyis_coordinator",
    "swarm_lead": "agyis_coordinator",
    # Planner
    "planner": "agyis_planner",
    "designer": "agyis_planner",
    "researcher": "agyis_planner",
    # Architect / Main
    "architect": "agyis_architect",
    "lead": "agyis_architect",
    "main": "agyis_architect",
    "psl_main": "agyis_architect",
    "psl-main": "agyis_architect",
    "general": "agyis_architect",
    "default": "agyis_architect",
    "master_implementer": "agyis_architect",
    "deep_hybrid": "agyis_architect",
    # Investigator
    "investigator": "agyis_investigator",
    "detective": "agyis_investigator",
    "forensic": "agyis_investigator",
    "root_cause_analyst": "agyis_investigator",
    "rca": "agyis_investigator",
}

# Canonical list of current agyis_* agent personas
CANONICAL_AGENTS = (
    "agyis_architect",
    "agyis_auditor",
    "agyis_builder",
    "agyis_coordinator",
    "agyis_custodian",
    "agyis_investigator",
    "agyis_planner",
    "agyis_reviewer",
)


def resolve_agent_name(name: str) -> str:
    """
    Resolve an agent name, alias, or legacy moniker to its canonical agyis_* name.
    If the name is already canonical or unrecognized, it is returned normalized.
    """
    norm = name.strip().lower().replace("-", "_")
    return LEGACY_AGENT_ALIASES.get(norm, norm)


__all__ = [
    "LEGACY_AGENT_ALIASES",
    "CANONICAL_AGENTS",
    "resolve_agent_name",
]
