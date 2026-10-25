# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unified Subagent Routing & Multi-Agent Execution Engine (ADR-019 / ADR-031 / Issue #92).

Codifies the 12 Canonical Autonomous Routing Workflows (Workflows A through L),
execution modes (LADDER, PARALLEL_FANOUT, TEAMWORK_DAG, BOOST_TOURNAMENT),
and typed stage transition payload generation and validation (psl_stage_transition_payload.json).
Zero external dependencies (100% Python Standard Library).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


class WorkflowMode(str, Enum):
    """Execution topology modes for multi-agent workflows."""
    LADDER = "LADDER"  # Sequential specialist quality gates (Investigator -> Planner -> Builder -> Reviewer -> Custodian -> Auditor)
    PARALLEL_FANOUT = "PARALLEL_FANOUT"  # Coordinator-led parallel research / diagnostic exploration
    TEAMWORK_DAG = "TEAMWORK_DAG"  # Native /teamwork-preview task graph with worktrees under .agents/teamwork/
    BOOST_TOURNAMENT = "BOOST_TOURNAMENT"  # Native /boost multi-perspective competition (owl DeepCoder + DeepInvestigator)


@dataclass(frozen=True)
class WorkflowRoute:
    """Typed specification for a canonical autonomous routing workflow."""
    letter: str
    alias: str
    mnemonic_aliases: Tuple[str, ...]
    title: str
    starting_specialist: str
    pipeline_route: str
    mode: WorkflowMode
    critical_invariants: str
    primary_deliverable: str
    empirical_precedent: str
    stage_sequence: Tuple[str, ...]
    default_artifacts: Dict[str, Optional[str]] = field(default_factory=dict)

    def matches(self, query: str) -> bool:
        """Returns True if the query matches the letter, primary alias, or mnemonic aliases."""
        q = query.strip().lower()
        if q == self.letter.lower():
            return True
        if q == self.alias.lower():
            return True
        return q in (a.lower() for a in self.mnemonic_aliases)


# The 12 Canonical Autonomous Routing Workflows (Workflows A through L)
CANONICAL_ROUTES: Tuple[WorkflowRoute, ...] = (
    WorkflowRoute(
        letter="A",
        alias="rca",
        mnemonic_aliases=("rca", "bugfix", "bug", "defect", "patch", "investigate"),
        title="Bug Report / Test Regression / Silent Failure",
        starting_specialist="agyis_investigator",
        pipeline_route="Investigator -> Planner -> Builder -> Reviewer -> Custodian -> Auditor",
        mode=WorkflowMode.LADDER,
        critical_invariants="Strict Read-Only on Code: Author scratch/reproduce_*.py before writing any fix.",
        primary_deliverable="rca_report.md + reproduce_bug.py",
        empirical_precedent="Live debugging of /compact interceptor bug (Steps 3580–3634)",
        stage_sequence=("INVESTIGATION", "PLANNING", "EXECUTION", "CODE_REVIEW", "GIT_CUSTODY", "QA_AUDIT", "PROMOTION"),
        default_artifacts={
            "plan_path": "implementation_plan.md",
            "reproduction_script": "scratch/reproduce_bug.py",
            "report_path": "rca_report.md",
        },
    ),
    WorkflowRoute(
        letter="B",
        alias="feature",
        mnemonic_aliases=("feature", "plan", "spec", "milestone", "design"),
        title="New Feature / Multi-File Milestone",
        starting_specialist="agyis_planner",
        pipeline_route="Planner -> Coordinator Lock-In -> Builder -> Reviewer -> Custodian -> Auditor",
        mode=WorkflowMode.LADDER,
        critical_invariants="Zero Speculative Code: Evaluates contracts and imports without touching source code.",
        primary_deliverable="implementation_plan.md",
        empirical_precedent="Epic #51 Phase 3.1 & Phase 3.3 planning",
        stage_sequence=("PLANNING", "EXECUTION", "CODE_REVIEW", "GIT_CUSTODY", "QA_AUDIT", "PROMOTION"),
        default_artifacts={
            "plan_path": "implementation_plan.md",
            "reproduction_script": None,
            "report_path": "plan_summary.md",
        },
    ),
    WorkflowRoute(
        letter="C",
        alias="laser",
        mnemonic_aliases=("laser", "builder", "single", "hotfix", "task"),
        title="Well-Defined Single-Phase Task",
        starting_specialist="agyis_builder",
        pipeline_route="Builder -> Reviewer -> Custodian -> Auditor",
        mode=WorkflowMode.LADDER,
        critical_invariants="Laser Executioner: Single contiguous replacements (replace_file_content). Zero scope creep.",
        primary_deliverable="In-flight diff + local test pass",
        empirical_precedent="Native slash command bypass patch (f13e63f)",
        stage_sequence=("EXECUTION", "CODE_REVIEW", "GIT_CUSTODY", "QA_AUDIT", "PROMOTION"),
        default_artifacts={
            "plan_path": None,
            "reproduction_script": None,
            "report_path": "diff_summary.md",
        },
    ),
    WorkflowRoute(
        letter="D",
        alias="overhaul",
        mnemonic_aliases=("overhaul", "architect", "refactor", "macro", "cross-module"),
        title="Cross-Module Architectural Overhaul",
        starting_specialist="agyis_architect",
        pipeline_route="Architect (delegates sub-parts) -> Reviewer -> Custodian -> Auditor",
        mode=WorkflowMode.LADDER,
        critical_invariants="Deep Hybrid Orchestration: Combines implementation with delegation to prevent context bloating past 50k tokens.",
        primary_deliverable="Clean multi-module pull request / diff",
        empirical_precedent="Issue #87 Subagent Ladder domain decoupling (a71c104)",
        stage_sequence=("PLANNING", "EXECUTION", "CODE_REVIEW", "GIT_CUSTODY", "QA_AUDIT", "PROMOTION"),
        default_artifacts={
            "plan_path": "implementation_plan.md",
            "reproduction_script": None,
            "report_path": "architecture_overhaul.md",
        },
    ),
    WorkflowRoute(
        letter="E",
        alias="heisenbug",
        mnemonic_aliases=("heisenbug", "flaky", "flake", "concurrency", "intermittent"),
        title="Heisenbug during Auditor QA Gate",
        starting_specialist="agyis_investigator",
        pipeline_route="Auditor (FAIL) -> Investigator (RCA) -> Builder (Fix) -> Reviewer -> Custodian -> Auditor",
        mode=WorkflowMode.LADDER,
        critical_invariants="Anti-Bypass Invariant: Remediations must re-traverse Hammer review and Custodian commit gate.",
        primary_deliverable="heisenbug_rca.md",
        empirical_precedent="SQLite WAL concurrency contention debugging",
        stage_sequence=("INVESTIGATION", "EXECUTION", "CODE_REVIEW", "GIT_CUSTODY", "QA_AUDIT", "PROMOTION"),
        default_artifacts={
            "plan_path": None,
            "reproduction_script": "scratch/reproduce_heisenbug.py",
            "report_path": "heisenbug_rca.md",
        },
    ),
    WorkflowRoute(
        letter="F",
        alias="regression",
        mnemonic_aliases=("regression", "side-effect", "breakage"),
        title="Obscure Regression during Macro Build",
        starting_specialist="agyis_architect",
        pipeline_route="Architect -> Investigator (RCA) -> Architect -> Reviewer -> Custodian -> Auditor",
        mode=WorkflowMode.LADDER,
        critical_invariants="Architect-to-Investigator Delegation: On mysterious test breakages, pause and delegate RCA instead of guess-editing.",
        primary_deliverable="scratch/reproduce_*.py + rca_report.md",
        empirical_precedent="PreInvocation locked DB handling",
        stage_sequence=("INVESTIGATION", "EXECUTION", "CODE_REVIEW", "GIT_CUSTODY", "QA_AUDIT", "PROMOTION"),
        default_artifacts={
            "plan_path": "implementation_plan.md",
            "reproduction_script": "scratch/reproduce_regression.py",
            "report_path": "regression_rca.md",
        },
    ),
    WorkflowRoute(
        letter="G",
        alias="research",
        mnemonic_aliases=("research", "fanout", "explore", "survey", "landscape"),
        title="Multi-Track Parallel Research / Landscape Mapping",
        starting_specialist="agyis_coordinator",
        pipeline_route="Coordinator -> Fan-out parallel Planners / Investigators -> Coordinator Synthesis",
        mode=WorkflowMode.PARALLEL_FANOUT,
        critical_invariants="Context Preservation (ADR-025): Independent research tracks run in parallel contexts without cross-contamination.",
        primary_deliverable="research_synthesis.md / track_*.md",
        empirical_precedent="Epic Research Kickoff (Steps 5–17: 4 parallel research tracks)",
        stage_sequence=("PLANNING", "INVESTIGATION", "PROMOTION"),
        default_artifacts={
            "plan_path": None,
            "reproduction_script": None,
            "report_path": "research_synthesis.md",
        },
    ),
    WorkflowRoute(
        letter="H",
        alias="cleanroom",
        mnemonic_aliases=("cleanroom", "spec-audit", "gap-ledger", "reverse-engineer"),
        title="Cleanroom Specification Audit & Gap Ledger",
        starting_specialist="agyis_investigator",
        pipeline_route="Investigator (Cleanroom Auditor) -> Coordinator -> Builder / Swarm",
        mode=WorkflowMode.LADDER,
        critical_invariants="Zero Production Mutation: Evaluates baseline line-by-line against formal ACs. Documents gaps in COMPLETION_LEDGER.md.",
        primary_deliverable="COMPLETION_LEDGER.md",
        empirical_precedent="Issue #83 Route C Baseline Audit (Step 2488)",
        stage_sequence=("INVESTIGATION", "PLANNING", "PROMOTION"),
        default_artifacts={
            "plan_path": None,
            "reproduction_script": None,
            "report_path": "COMPLETION_LEDGER.md",
        },
    ),
    WorkflowRoute(
        letter="I",
        alias="merge",
        mnemonic_aliases=("merge", "reconcile", "golden-merge", "cross-branch"),
        title="Cross-Branch Golden Merge & Reconciliation",
        starting_specialist="agyis_architect",
        pipeline_route="Architect (Synthesizer) -> Reviewer -> Custodian -> Auditor",
        mode=WorkflowMode.LADDER,
        critical_invariants="Hermetic Worktree Isolation: Reconciles divergent branches in dedicated worktree. Runs cross-test matrix.",
        primary_deliverable="Golden commit on unified feature branch",
        empirical_precedent="Epic #51 Phase 3.1 Route A vs Route B Golden Merge (Steps 1505 & 1603)",
        stage_sequence=("EXECUTION", "CODE_REVIEW", "GIT_CUSTODY", "QA_AUDIT", "PROMOTION"),
        default_artifacts={
            "plan_path": "merge_plan.md",
            "reproduction_script": None,
            "report_path": "merge_reconciliation.md",
        },
    ),
    WorkflowRoute(
        letter="J",
        alias="victory",
        mnemonic_aliases=("victory", "certification", "dual-audit", "release-gate"),
        title="Out-of-Band Victory Certification Council",
        starting_specialist="agyis_auditor",
        pipeline_route="Auditor (Hermetic Benchmarks) + Reviewer (8 Rules) -> Dual Sign-Off",
        mode=WorkflowMode.LADDER,
        critical_invariants="Dual-Auditor Gate: Never trust in-band self-certification. Independent auditors evaluate clean committed revision on HEAD.",
        primary_deliverable="victory_audit_report.md",
        empirical_precedent="Route A, B, and C Victory Audits (Steps 993, 2106, 3634, 3781)",
        stage_sequence=("CODE_REVIEW", "QA_AUDIT", "PROMOTION"),
        default_artifacts={
            "plan_path": None,
            "reproduction_script": None,
            "report_path": "victory_audit_report.md",
        },
    ),
    WorkflowRoute(
        letter="K",
        alias="governance",
        mnemonic_aliases=("governance", "issues", "curation", "epic", "github"),
        title="Milestone Governance & GitHub Issue Curation",
        starting_specialist="agyis_custodian",
        pipeline_route="Flight Director / Coordinator -> Custodian (Issue Formulation & Epic Sync via gh CLI)",
        mode=WorkflowMode.LADDER,
        critical_invariants="Zero Repository Document Pollution (AC5): Strictly zero scratch notes in git tree; deterministic CLI execution via gh.",
        primary_deliverable="GitHub Issues + Parent Epic Tracking Comment",
        empirical_precedent="Phase 3.3 GitHub Issue Harmonizer (Step 2095: Created #83, #84, #85 and synced Epic #51)",
        stage_sequence=("PLANNING", "PROMOTION"),
        default_artifacts={
            "plan_path": None,
            "reproduction_script": None,
            "report_path": "milestone_governance_report.md",
        },
    ),
    WorkflowRoute(
        letter="L",
        alias="fuzz",
        mnemonic_aliases=("fuzz", "adversarial", "stress", "hardening"),
        title="Adversarial Fuzzing & Stress Hardening Battery",
        starting_specialist="agyis_builder",
        pipeline_route="Investigator (Fuzzing Vectors) -> Builder (Adversarial Tests) -> Reviewer -> Custodian -> Auditor",
        mode=WorkflowMode.LADDER,
        critical_invariants="Zero Error Swallowing & Sub-Second SLA: Concurrency lock timeout <=0.5s, schema corruption tests must fail-open cleanly.",
        primary_deliverable="tests/test_*_adversarial.py",
        empirical_precedent="Route C Carrier-Grade Hardening (Step 2990: 4 adversarial hardening vectors)",
        stage_sequence=("INVESTIGATION", "EXECUTION", "CODE_REVIEW", "GIT_CUSTODY", "QA_AUDIT", "PROMOTION"),
        default_artifacts={
            "plan_path": None,
            "reproduction_script": "scratch/fuzz_vector.py",
            "report_path": "hardening_report.md",
        },
    ),
)


def list_routes() -> List[WorkflowRoute]:
    """Returns a list of all 12 Canonical Routing Workflows."""
    return list(CANONICAL_ROUTES)


def get_route(query: str) -> Optional[WorkflowRoute]:
    """Finds a Canonical Routing Workflow by letter, primary alias, or mnemonic alias."""
    for r in CANONICAL_ROUTES:
        if r.matches(query):
            return r
    return None


def build_stage_transition_payload(
    task_id: str,
    phase: str,
    stage: str,
    status: str = "PASS",
    sender_role: str = "cockpit_director",
    next_recommended_stage: Optional[str] = None,
    git_commit_hash: str = "HEAD",
    modified_files: Optional[List[str]] = None,
    added_lines: int = 0,
    deleted_lines: int = 0,
    contiguous_chunks_count: int = 0,
    command: str = "./agyis test",
    exit_code: int = 0,
    total_tests: int = 0,
    passed_tests: int = 0,
    failed_tests: int = 0,
    benchmark_latency_s: float = 0.0,
    plan_path: Optional[str] = None,
    reproduction_script: Optional[str] = None,
    report_path: Optional[str] = None,
    defect_ledger: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Constructs a valid psl_stage_transition_payload.json dictionary compliant with
    PSL-SPEC-2026-COCKPIT-DIRECTOR-001 Pillar 3.3.
    """
    stage_upper = stage.upper().strip()
    next_stage = (next_recommended_stage or stage_upper).upper().strip()

    return {
        "protocol_version": "2026.1",
        "task_id": task_id,
        "phase": phase,
        "stage": stage_upper,
        "status": status.upper().strip(),
        "sender_role": sender_role,
        "next_recommended_stage": next_stage,
        "git_commit_hash": git_commit_hash,
        "diff_summary": {
            "modified_files": modified_files or [],
            "added_lines": max(0, int(added_lines)),
            "deleted_lines": max(0, int(deleted_lines)),
            "contiguous_chunks_count": max(0, int(contiguous_chunks_count)),
        },
        "verification": {
            "command": command,
            "exit_code": int(exit_code),
            "total_tests": max(0, int(total_tests)),
            "passed_tests": max(0, int(passed_tests)),
            "failed_tests": max(0, int(failed_tests)),
            "benchmark_latency_s": max(0.0, float(benchmark_latency_s)),
        },
        "artifacts": {
            "plan_path": plan_path,
            "reproduction_script": reproduction_script,
            "report_path": report_path,
        },
        "defect_ledger": defect_ledger or [],
    }


def validate_stage_transition_payload(payload: Any) -> Tuple[bool, List[str]]:
    """
    Validates a stage transition payload dictionary against schema invariants.
    Returns (is_valid, list_of_error_strings).
    """
    errors: List[str] = []
    if not isinstance(payload, dict):
        return False, ["Payload must be a JSON dictionary."]

    required_keys = (
        "protocol_version", "task_id", "phase", "stage", "status",
        "sender_role", "next_recommended_stage", "git_commit_hash",
        "diff_summary", "verification", "artifacts"
    )
    for k in required_keys:
        if k not in payload:
            errors.append(f"Missing required key: '{k}'")

    if payload.get("protocol_version") != "2026.1":
        errors.append(f"Invalid protocol_version: expected '2026.1', got {payload.get('protocol_version')!r}")

    diff = payload.get("diff_summary")
    if not isinstance(diff, dict):
        errors.append("'diff_summary' must be a dictionary.")
    else:
        for dk in ("modified_files", "added_lines", "deleted_lines", "contiguous_chunks_count"):
            if dk not in diff:
                errors.append(f"Missing diff_summary key: '{dk}'")

    verif = payload.get("verification")
    if not isinstance(verif, dict):
        errors.append("'verification' must be a dictionary.")
    else:
        for vk in ("command", "exit_code", "total_tests", "passed_tests", "failed_tests", "benchmark_latency_s"):
            if vk not in verif:
                errors.append(f"Missing verification key: '{vk}'")

    arts = payload.get("artifacts")
    if not isinstance(arts, dict):
        errors.append("'artifacts' must be a dictionary.")
    else:
        for ak in ("plan_path", "reproduction_script", "report_path"):
            if ak not in arts:
                errors.append(f"Missing artifacts key: '{ak}'")

    return len(errors) == 0, errors


def format_route_briefing(route: WorkflowRoute, task_id: str = "TASK-001") -> str:
    """Formats a clean terminal/markdown dispatch briefing for the specified route."""
    template_payload = build_stage_transition_payload(
        task_id=task_id,
        phase=f"Phase: {route.title}",
        stage=route.stage_sequence[0],
        sender_role="cockpit_director",
        next_recommended_stage=route.stage_sequence[1] if len(route.stage_sequence) > 1 else route.stage_sequence[0],
        plan_path=route.default_artifacts.get("plan_path"),
        reproduction_script=route.default_artifacts.get("reproduction_script"),
        report_path=route.default_artifacts.get("report_path"),
    )

    aliases_str = ", ".join(route.mnemonic_aliases)
    return (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛫 ROUTE {route.letter}: {route.title.upper()}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• Mode               : {route.mode.value}\n"
        f"• Entry Specialist   : {route.starting_specialist}\n"
        f"• Ladder Sequence    : {route.pipeline_route}\n"
        f"• Mnemonic Aliases   : {aliases_str}\n"
        f"• Invariant Boundary : {route.critical_invariants}\n"
        f"• Primary Deliverable: {route.primary_deliverable}\n"
        f"• Empirical Precedent: {route.empirical_precedent}\n"
        f"\n"
        f"📋 STAGE TRANSITION DISPATCH TEMPLATE (psl_stage_transition_payload.json):\n"
        f"```json\n"
        f"{json.dumps(template_payload, indent=2)}\n"
        f"```\n"
    )
