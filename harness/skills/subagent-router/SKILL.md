---
name: subagent-router
description: >-
  Dynamic subagent routing and multi-agent SWE execution protocol. Coordinates specialized
  agent pipelines (Investigator -> Planner -> Builder -> Reviewer -> Custodian -> Auditor)
  across the 12 canonical workflows, native Antigravity teamwork graphs, and tournament boosts.
  Callable manually via /subagent-router (or /subagent-ladder) or dispatched downstream by Cockpit Flight Directors.
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Subagent Router: Dynamic Multi-Agent SWE Execution Protocol 🤖🧭

The **Subagent Router** (formerly known as `subagent-ladder`) formalizes the dynamic multi-agent execution engine for complex software engineering milestones, architectural refactorings, and multi-node delivery campaigns in Agyis Harness.

Rather than enforcing a rigid 1-dimensional waterfall, the Subagent Router dynamically routes engineering tasks through specialized `agyis_*` agents across **12 canonical workflows** and **4 distinct execution modes** (Sequential Quality Gates, Parallel Fan-Out, Native Teamwork Task DAGs, and Tournament Boosts).

> [!NOTE]
> **Invocation Contracts**:
> - **Upstream Cockpit Dispatch**: Naturally dispatched downstream by the **Cockpit Flight Director** (`cockpit-director`) via typed stage transition payloads (`psl_stage_transition_payload.json`).
> - **Operator / Manual Engagement**: Can also be engaged directly by human operators using `/subagent-router` (or legacy `/subagent-ladder`), or via `agyis cockpit route <letter>`.
> - **Specialist Orchestration**: Coordinated by `agyis_coordinator` (for assembly lines and research fan-outs) or `agyis_architect` (for cross-module overhauls).

---

## 1. Architectural Rationale & Dual-Sovereignty Model

Complex engineering initiatives easily cause **conversational context collapse** when executed in a single monolithic context window. Accumulated tool outputs, compile logs, and search results bloat context, degrade instruction following, and incur exponential token costs.

The Subagent Router enforces the **Dual-Sovereignty Principle** (Cognition vs. Harness):
- **Cognition governs reasoning, intent, and architectural synthesis**: Role-pinning mental models, falsifiable root-cause hypotheses, surgical laser implementation, and dual-auditor certification.
- **The Harness governs boundaries, state verification, and physical execution guarantees**: Deterministic pre-tool-use write blocks for read-only agents, terminal command safety, output compaction (<2KB), and completion fence verification gates.

Key cognitive benefits include:
1. **Zero Context Carryover**: Subagents operate in lean, task-focused contexts (<50k tokens), preserving high reasoning capability and deterministic instruction following.
2. **Cognitive Role Isolation**: Separates the builder from the reviewer. An agent that writes code never reviews or audits its own diffs.
3. **Hermetic State Preservation**: High-level milestone state, plan artifacts, and empirical test logs are preserved in persistent markdown documents, resilient to conversational compaction or session resets.
4. **Anti-Anchoring Invariant**: Reviewers and auditors approach incoming diffs skeptically to break them with real repository tests rather than passively confirming prior attempts.

---

## 2. Autonomous Routing Architecture & 12-Workflow Decision Table

The Subagent Router provides dynamic, autonomous routing across specialized `agyis_*` agents based on the operational profile of the incoming task.

For the complete visual flowchart and exhaustive 12-workflow decision matrix, see:
- 🗺️ **[Workflow Routing Table & Decision Matrix](references/workflow-routing-table.md)**: Full visual topology and formal decision table for Workflows A through L.

### Summary of Canonical Workflow Signatures:
- **Workflow A (Bug Report / Test Regression)**: `Investigator -> Planner -> Builder -> Reviewer -> Custodian -> Auditor`
- **Workflow B (New Feature / Multi-File Milestone)**: `Planner -> Coordinator Lock-In -> Builder -> Reviewer -> Custodian -> Auditor`
- **Workflow C (Well-Defined Single-Phase Task)**: `Builder -> Reviewer -> Custodian -> Auditor`
- **Workflow D (Cross-Module Architectural Overhaul)**: `Architect (delegates sub-parts) -> Reviewer -> Custodian -> Auditor`
- **Workflow E (Heisenbug during Auditor QA Gate)**: `Auditor (FAIL) -> Investigator (RCA) -> Builder (Fix) -> Reviewer -> Custodian -> Auditor`
- **Workflow F (Obscure Regression during Macro Build)**: `Architect -> Investigator (RCA) -> Architect -> Reviewer -> Custodian -> Auditor`
- **Workflow G (Multi-Track Parallel Research)**: `Coordinator -> Parallel Fan-Out (Planner + Investigator) -> Coordinator Synthesis`
- **Workflow H (Cleanroom Specification Audit)**: `Investigator (Cleanroom Auditor) -> Coordinator -> Builder / Swarm`
- **Workflow I (Cross-Branch Golden Merge)**: `Architect (Synthesizer) -> Reviewer -> Custodian -> Auditor`
- **Workflow J (Out-of-Band Victory Certification Council)**: `Auditor + Reviewer -> Dual Sign-Off Gate`
- **Workflow K (Milestone Governance & GitHub Issue Curation)**: `Flight Director / Coordinator -> Custodian (Issue Formulation & Epic Sync)`
- **Workflow L (Adversarial Fuzzing & Stress Hardening)**: `Investigator -> Builder -> Reviewer -> Custodian -> Auditor`

---

## 3. The 6-Stage Pipeline Lifecycle

Every engineering milestone progressing through the sequential execution path advances through the **6-Stage Pipeline**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: PLANNING & OPERATOR LOCK-IN (`agyis_coordinator` / `agyis_planner`) │
│ - `agyis_planner` synthesizes architecture into `implementation_plan.md`.│
│ - Operator reviews, grills, refines, and formally locks in the plan.    │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ (Approved)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STAGE 2: SURGICAL EXECUTION (`agyis_builder` / `agyis_architect`)       │◄────────────────────────┐
│ - `agyis_builder` applies surgical contiguous edits (`replace_file_content`). │                     │
│ - Local self-verification via native tests (<1.0s benchmark invariant).  │                         │
│ - Produces diff summary and local test pass.                            │                         │
└────────────────────────────────────┬────────────────────────────────────┘                         │
                                     │ (Execution Complete OR Remedy Complete)                      │
                                     ▼                                                              │
┌─────────────────────────────────────────────────────────────────────────┐                         │
│ STAGE 3: CODE REVIEW & QUALITY AUDIT (`agyis_reviewer` - The Hammer)    │                         │
│ - Independent agent audits diff against 8 Canonical Empirical Rules.    │                         │
│ - Zero Error Swallowing Invariant & Zero Self-Certification.            │                         │
│ - Emits PASS verdict OR Defect Ledger with file/line/rule citations.   │                         │
└────────────────────────────────────┬────────────────────────────────────┘                         │
                                     │                                                              │
         ┌───────────────────────────┴───────────────────────────┐                                  │
         │ (Passed Code Review)                                  │ (Rejected: Defect Ledger)        │
         ▼                                                       └──────────────────────────────────┤
┌─────────────────────────────────────────────────────────────────────────┐                         │
│ STAGE 4: MACRO ARCHITECTURAL AUDIT & GIT COMMIT GATE (`agyis_custodian`)│                         │
│ - 4-Pillar Quality Gate (DRY, AFF, Asset Decoupling, Git Porcelain).     │                         │
│ - Executes `agyis audit aff` (zero boundary breaches, cycles, monoliths)│                         │
│ - Stages ONLY target files declared in approved plan (no blind `git add`).│                         │
│ - Asserts working tree is 100% clean of scratch debris (AC5).           │                         │
│ - Executes atomic commit on HEAD.                                       │                         │
└────────────────────────────────────┬────────────────────────────────────┘                         │
                                     │ (Committed Cleanly)                                          │
                                     ▼                                                              │
┌─────────────────────────────────────────────────────────────────────────┐                         │
│ STAGE 5: HERMETIC QA & VERIFICATION AUDIT (`agyis_auditor`)             │                         │
│ - Strictly evaluates the COMMITTED git revision on HEAD (never dirty).  │                         │
│ - Runs project native test suite (`agyis test`, `pnpm test`, etc.).     │                         │
│ - Asserts exit code 0 and sub-second benchmark latency (<1.0s SLA).     │                         │
└──────────────────┬───────────────────────────────┘                                                │
                   │                                                                                │
         ┌─────────┴─────────┐                                                                      │
         │ (Passed QA Audit) │ (QA/Audit Failed)       ─────────────────────────────────────────────┘
         │                   │                                 (MANDATORY: Return to Builder/Investigator,
         ▼                   │                                 THEN through Hammer!)
┌────────────────────────────┴────────────────────────────────────────────┐
│ STAGE 6: PHASE ARCHIVAL & PROMOTION (`cockpit_director` / `agyis_coordinator`) │
│ - Archives milestone plan into `.agents/artifacts/phase_X_delivery.md`. │
│ - Records milestone completion in `docs/taxonomy/project-ledger.md`.     │
│ - Subagents for completed phase are formally retired.                   │
│ - Presents Phase X+1 Implementation Plan to user.                       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Multi-Node Swarm PR Ingestion Protocol

When coordinating distributed campaigns across parallel feature worktrees, multi-agent branches, or remote contributor PRs, follow the formal [Multi-Node Swarm PR Ingestion Protocol](references/swarm-pr-ingestion.md) (`gh pr list`, `gh pr diff`) to discover, fetch, isolate, audit, and merge branch deliverables with zero dirty-tree mutations.

---

## 5. Strict State Machine Invariants

### 5.1 Anti-Bypass Invariant (Zero Shortcuts)
> [!CAUTION]
> If `agyis_auditor` detects a failure and `agyis_builder` produces a remedy patch:
> $$\text{Auditor FAIL} \longrightarrow \text{Builder (Remedy)} \longrightarrow \mathbf{Reviewer\ (The\ Hammer\ Re\text{-}Review)} \longrightarrow \mathbf{Custodian\ (Commit\ Gate)} \longrightarrow \text{Auditor (QA)}$$
> **Under NO circumstances may an Executioner remedy bypass Hammer review or Custodian commit gate.** An implementer fixing an edge case under test failure pressure is prone to introducing error-swallowing constructs or artificial mocks. Auditor must audit strictly the clean, committed revision.

### 5.2 Zero Coordinator Remediation Invariant
> [!CRITICAL]
> The Coordinator (`agyis_coordinator`) is **strictly forbidden from modifying product code, patching files directly, or self-resolving review defects**.
> - The Coordinator orchestrates the ladder, manages persistent artifacts, and routes diagnostics.
> - Defect reports must be routed back to the designated `agyis_builder`.

### 5.3 Macro Architectural Audit & Git Commit Gate (The Custodian Mandate)
> [!IMPORTANT]
> The Custodian (`agyis_custodian`) is the sole entity authorized to stage and commit milestone deliverables, operating as the **4-Pillar Architectural & Git Commit Gate**:
> 1. **Pillar 4.1: DRY & Deduplication Audit**: Custodian sweeps repo (`grep_search`, `find_by_name`) to verify newly introduced helpers, utilities, and constants do NOT duplicate existing logic.
> 2. **Pillar 4.2: Architectural Fitness Gate (`agyis audit aff`)**: Custodian executes the native AFF engine to assert zero boundary breaches (ADR-014 bifurcation), zero dependency cycles, zero foreign language monoliths, and zero unbounded state caches.
> 3. **Pillar 4.3: Packaging & Asset Decoupling Audit**: Verify non-native assets (HTML, CSS, SQL, client JS scripts, templates, icons) are cleanly decoupled into dedicated `assets/` directories and declared in packaging manifests.
> 4. **Pillar 4.4: Git Porcelain & Atomic Staging Gate**: Verify porcelain tree status (`git status --porcelain`), deliberately stage only files specified in the approved plan (never blind `git add .`), and seal an atomic conventional commit on HEAD.
> - **Clean Revision Invariant**: The Auditor must certify a **committed git revision**, never a volatile, dirty working tree.
> - **Zero Scratch Debris (AC5)**: Telemetry databases, temporary logs, and scratch artifacts must never be staged into version control.
> - **Zero Direct Code Mutation**: The Custodian cannot modify product or test code (`write: false`).

### 5.4 Architectural Rejection Protocol
> [!CAUTION]
> If `agyis_custodian` detects a Pillar 4.1 duplication, a Pillar 4.2 architectural defect (`agyis audit aff` failure), or a Pillar 4.3 packaging coupling defect:
> $$\text{Custodian REJECT} \longrightarrow \mathbf{Builder\ (Remediation)} \longrightarrow \mathbf{Reviewer\ (The\ Hammer\ Re\text{-}Review)} \longrightarrow \mathbf{Custodian\ (Re\text{-}Audit)}$$
> - **Immediate Stage Rejection**: Custodian immediately halts the commit gate, aborts staging, and generates an Architectural Defect Report detailing exact boundary violations, cyclic imports, or embedded foreign language monoliths.
> - **Mandatory Return to Stage 2**: Remediation must be performed by `agyis_builder`.
> - **Hammer Re-Review Requirement**: Remediated diffs must re-traverse Hammer review (`agyis_reviewer`) before returning to Custodian.
> - **Zero Bypass to Auditor**: Under no circumstances may an architectural failure or boundary violation be bypassed to Stage 5 Auditor.

---

## 6. The 4 Multi-Agent Execution Modes

The Subagent Router supports 4 distinct execution topologies:

1. **`LADDER` (Sequential Specialist Quality Gates)**:
   - The default sequential path: `Builder -> Reviewer -> Custodian -> Auditor`.
   - Used for production code modifications where independent quality gates prevent regression.
2. **`PARALLEL_FANOUT` (Coordinator Diagnostic Exploration)**:
   - Used for Workflow G (Multi-Track Parallel Research).
   - `agyis_coordinator` dispatches parallel read-only planners and investigators in isolated contexts.
   - Findings are chiseled into persistent reports and synthesized by the Coordinator.
3. **`TEAMWORK_DAG` (Native `/teamwork` Task Graphs)**:
   - Native Antigravity multi-agent directed acyclic graph (DAG).
   - Spawns parallel worker worktrees under `.agents/teamwork/<agent_name>/`.
   - Liveness is tracked via `progress.md` heartbeats.
4. **`BOOST_TOURNAMENT` (Native `/boost` Multi-Perspective Synthesis)**:
   - Native Antigravity tournament mode pairing DeepCoder (`owl`) and DeepInvestigator.
   - Evaluates alternative architectural solutions through competitive reasoning before synthesis.

---

## 7. Interactive CLI Routing Integration & Swarm Monitoring

```bash
# 🛫 Canonical Workflow Routing
agyis router <route>                          # Dynamic subagent router CLI alias (e.g., agyis router victory)
agyis ladder <route>                          # Backwards-compatible router CLI alias (e.g., agyis ladder builder)
agyis cockpit route A                         # Route Workflow A (Bugfix / RCA)
agyis cockpit route B                         # Route Workflow B (New Feature Milestone)
agyis cockpit route <letter|alias>            # Route by letter (A–L) or alias (rca, builder, victory)
agyis cockpit route <letter> --json           # Machine-readable dispatch payload template

# 📋 View Registered Workflows & Execution Modes
agyis cockpit status                          # Flight deck overview & active subagents

# 🩺 Swarm Liveness & Delegate Monitoring Loops
agyis subagents --liveness                    # Deterministic delegate heartbeat inspection & liveness audit
agyis subagents --liveness --stale-threshold 300 # Detect stalled or dead workers in multi-agent swarms
agyis subagents --liveness --json             # Machine-readable liveness ledger for automated orchestration guards
```

### Swarm Monitoring Invariant
Orchestrators and coordinators must run `agyis subagents --liveness` in monitoring loops when awaiting delegate progress. If a delegate subagent stalls into `STALE` (>300s) or `DEAD` (>1800s) state without an active pause gate, the orchestrator must halt and intervene rather than hallucinating progress updates.
