<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Agyis Cockpit Flight Director: Operational Living Contract & Track C Standard

**Document Identifier**: `PSL-SPEC-2026-COCKPIT-DIRECTOR-001`  
**Classification**: Authoritative System Living Contract & Track C Standard  
**Governing ADRs**: ADR-012 (Artifact-First Planning), ADR-013 (Terminal Invariants), ADR-014 (Product vs. Project Bifurcation), ADR-015 (Clean-Room Testing & Verification), ADR-028 (Cleanroom Reconstruction), ADR-031 (Native Orchestration Alignment), ADR-032 (Tool-Native Primacy & Anti-Polling)  
**System Target**: Google Antigravity (Cortex/Jetski CL `951519500`, client v2.19.1+) & Agyis Harness (`psl-agy-harness`)  
**Status**: APPROVED & LOCKED  
**Date**: October 25, 2026  

---

## Executive Summary & Architectural Mandate

In enterprise-scale, autonomous software engineering (SWE), multi-agent systems routinely degrade when the root conversational interface attempts to execute continuous code edits, raw file mutations, and dense debugging loops directly in the primary context window. 

Under the **Track C (Long-Horizon Autonomous Engineering)** operational regime, this document codifies the non-negotiable living contract governing root pairing sessions between human software architects and the **Agyis Cockpit Flight Director** (`cockpit_director`).

```mermaid
flowchart TD
    subgraph OperatorSpace["Human Operator Space"]
        OP["Human Software Architect / Operator"]
    end

    subgraph CockpitSpace["Root Pairing Cockpit (Track C Flight Direction)"]
        FD["Cockpit Flight Director<br/>(Air Traffic Control Tower)"]
        PLAN["Artifact-First Planning<br/>(implementation_plan.md)"]
        CONFIRM["Proactive Confirmation Gates<br/>(Destructive & Release Actions)"]
        FD --- PLAN
        FD --- CONFIRM
    end

    subgraph SpecialistLadder["Agyis Subagent Ladder (Isolated Worktrees & Execution Contexts)"]
        COORD["agyis_coordinator<br/>(Assembly Line Lead)"]
        INV["agyis_investigator<br/>(Forensic RCA & Scratch Tests)"]
        PLANNER["agyis_planner<br/>(Dependency & Architecture Plan)"]
        BUILD["agyis_builder<br/>(Laser Executioner)"]
        REV["agyis_reviewer<br/>(The Hammer: Rule Audit)"]
        CUST["agyis_custodian<br/>(DRY Staging & HEAD Git Commit)"]
        AUD["agyis_auditor<br/>(Victory Auditor: Sub-Second Benchmarks)"]
        ARCH["agyis_architect<br/>(Deep Hybrid Systems Lead)"]
    end

    OP <-->|"High-Level Strategic Direction & Options (Plane 1)"| FD
    FD <-->|"Typed Stage Transition Payloads (Plane 2)"| COORD
    COORD --> INV
    COORD --> PLANNER
    COORD --> BUILD
    COORD --> ARCH
    BUILD --> REV
    ARCH --> REV
    REV --> CUST
    CUST --> AUD
    AUD -->|"Certified Milestone Hand-off"| FD
```

### The Air Traffic Control Tower Mandate
> **The Root Cockpit is an Air Traffic Control Tower, not a construction site.**  
> In long-horizon pairing sessions, the primary cockpit context window is the most valuable and fragile asset in the cognitive topology. It exists strictly to maintain situational awareness, conduct human-in-the-loop steering, evaluate trade-offs, and dispatch autonomous subagent ladders. It does not lay bricks, pour concrete, or swing hammers.

### The Empirical Context Cliff
Empirical telemetry extracted across 1,065+ production sessions in the PSL telemetry laboratory demonstrates an unyielding law of cognitive trajectory health:
- **Healthy Zone (<50k tokens / <50 steps)**: Sessions exhibit an error rate of only **0.8 errors per session**. Cognitive reasoning, instruction fidelity, and architectural synthesis operate at peak reliability.
- **Degradation Zone (50k–180k tokens / 50–150 steps)**: Instruction drift begins; models become susceptible to subtle prompt omissions and synthetic self-certification.
- **The Context Cliff (>200 steps / >230k tokens)**: Sessions suffer a catastrophic **20x error spike**. Models thrash on previously resolved bugs, hallucinate tool states, attempt forbidden writes, and trigger emergency compaction.

Every line of product code written directly in the root cockpit, every unfiltered terminal output dumped into the pairing prompt, and every failed test trace digested in the main window accelerates the descent toward the context cliff. Track C eliminates this vulnerability by enforcing total architectural separation between Flight Direction and Specialist Execution.

---

## Pillar 1: Cockpit Zero-Code-Thrash Invariant

The Cockpit Flight Director is bound by an absolute prohibition against continuous code editing, in-line test debugging, and multi-line script execution in the root conversation window.

### 1.1 Forbidden Root Anti-Patterns
1. **Zero Code File Mutation**: The Flight Director must never call `replace_file_content` or `write_to_file` on product source files (`harness/**`, `src/**`, `lib/**`, `tests/**`). Direct code mutations are deterministically blocked by the PreToolUse `anti_drift_hook` for flight director roles.
2. **Zero Dense In-Line Debugging**: The Flight Director must never analyze 500-line compiler errors, test failure stack traces, or binary coredumps in the root context. Diagnostic analysis belongs exclusively in Tier 2 scratch scripts executed by `agyis_investigator`.
3. **Zero Standalone Terminal Bash One-Liners**: Complex shell logic, multi-command pipelines, and sed/awk manipulations must never be executed via bash `-c` in root turns. Operational scripts must be written to `<appDataDir>/brain/<id>/scratch/` and executed as hermetic files.
4. **Zero Exploration Sweeps**: The Flight Director must never execute unbounded `list_dir` or `find_by_name` sweeps across the repository.

### 1.2 Dedicated Scope of the Root Cockpit
Root pairing context is preserved strictly for:
1. **High-Level Strategic Direction**: Milestone decomposition, requirements clarification, domain modeling, and user journey synthesis.
2. **Human-in-the-Loop Steering**: Reviewing architectural options with the human operator, evaluating trade-offs, and seeking explicit confirmation on irreversible operations.
3. **Subagent Ladder Dispatch & Governance**: Invoking specialized subagent pipelines (`agyis_planner`, `agyis_investigator`, `agyis_builder`, etc.), monitoring milestone progress via reactive wakeups, and enforcing the Dual-Auditor Gate.
4. **Living Artifact Maintenance**: Updating `implementation_plan.md`, `project_ledger.md`, and `roadmap.md` (<50 lines retroactive compaction).

---

## Pillar 2: The 12 Canonical Autonomous Routing Workflows

When the operator presents an objective, defect, or architectural mandate, the Cockpit Flight Director classifies the request into one of the **12 Canonical Autonomous Routing Workflows** (Workflows A through L) and dispatches the appropriate subagent pipeline:

```mermaid
flowchart TD
    START["Operator Objective / Trigger"] --> CLASS{"Classify Signature"}

    CLASS -- "Bug / Regression" --> WA["Workflow A: agyis_investigator (RCA First)"]
    CLASS -- "New Feature Milestone" --> WB["Workflow B: agyis_planner (Plan First)"]
    CLASS -- "Single-Phase Task" --> WC["Workflow C: agyis_builder (Direct Execution)"]
    CLASS -- "Cross-Module Overhaul" --> WD["Workflow D: agyis_architect (Deep Hybrid)"]
    CLASS -- "Auditor QA Failure" --> WE["Workflow E: agyis_investigator (Heisenbug)"]
    CLASS -- "Macro Build Break" --> WF["Workflow F: agyis_architect -> investigator"]
    CLASS -- "Landscape Research" --> WG["Workflow G: agyis_coordinator (Parallel Fan-out)"]
    CLASS -- "Cleanroom Spec Audit" --> WH["Workflow H: agyis_investigator (Ledger Audit)"]
    CLASS -- "Branch Merge & Reconciliation" --> WI["Workflow I: agyis_architect (Golden Worktree)"]
    CLASS -- "Out-of-Band Sign-Off" --> WJ["Workflow J: Dual-Auditor Council (HEAD Audit)"]
    CLASS -- "Issue & Epic Sync" --> WK["Workflow K: agyis_custodian (gh CLI Governance)"]
    CLASS -- "Fuzzing & Hardening" --> WL["Workflow L: agyis_investigator + builder"]

    WA --> COORD_PIPE["Subagent Assembly Pipeline"]
    WB --> COORD_PIPE
    WC --> COORD_PIPE
    WD --> COORD_PIPE
    WE --> COORD_PIPE
    WF --> COORD_PIPE
    WG --> COORD_PIPE
    WH --> COORD_PIPE
    WI --> COORD_PIPE
    WJ --> COORD_PIPE
    WK --> COORD_PIPE
    WL --> COORD_PIPE
```

### 2.1 The Master Routing Decision Matrix

| Workflow Profile & Signature | Starting Specialist | Pipeline Route | Critical Invariants & Tool Boundaries | Primary Deliverable Artifact | Empirical Precedent |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A. Bug Report / Test Regression / Silent Failure** | `agyis_investigator` | `Investigator` $\rightarrow$ `Planner` $\rightarrow$ `Builder` $\rightarrow$ `Reviewer` $\rightarrow$ `Custodian` $\rightarrow$ `Auditor` | **Strict Read-Only on Code**: Must author a deterministic reproduction script in scratch (`scratch/reproduce_*.py`) before writing any fix. | `rca_report.md` + `reproduce_bug.py` | Live debugging of `/compact` interceptor bug (Steps 3580–3634) |
| **B. New Feature / Multi-File Milestone** | `agyis_planner` | `Planner` $\rightarrow$ `Coordinator Lock-In` $\rightarrow$ `Builder` $\rightarrow$ `Reviewer` $\rightarrow$ `Custodian` $\rightarrow$ `Auditor` | **Zero Speculative Code**: Evaluates imports, architecture, and contracts without touching source code. Drafts interactive implementation plan. | `implementation_plan.md` | Epic #51 Phase 3.1 & Phase 3.3 planning |
| **C. Well-Defined Single-Phase Task** | `agyis_builder` | `Builder` $\rightarrow$ `Reviewer` $\rightarrow$ `Custodian` $\rightarrow$ `Auditor` | **Laser Executioner**: Single contiguous replacements (`replace_file_content`). Zero scope creep. Self-verifies locally. | In-flight diff + local test pass | Native slash command bypass patch (`f13e63f`) |
| **D. Cross-Module Architectural Overhaul** | `agyis_architect` | `Architect` (delegates sub-parts) $\rightarrow$ `Reviewer` $\rightarrow$ `Custodian` $\rightarrow$ `Auditor` | **Deep Hybrid Orchestration**: Combines implementation with delegation to `agyis_planner` and `agyis_builder` to prevent context bloating past 50k tokens. | Clean multi-module pull request / diff | Issue #87 Subagent Ladder domain decoupling (`a71c104`) |
| **E. Heisenbug during Auditor QA Gate** | `agyis_investigator` | `Auditor (FAIL)` $\rightarrow$ `Investigator (RCA)` $\rightarrow$ `Builder (Fix)` $\rightarrow$ `Reviewer` $\rightarrow$ `Custodian` $\rightarrow$ `Auditor` | **Anti-Bypass Invariant**: Under no circumstances may an Auditor failure bypass Hammer re-review or Custodian commit gate after being remediated. | `heisenbug_rca.md` | SQLite WAL concurrency contention debugging |
| **F. Obscure Regression during Macro Build** | `agyis_architect` | `Architect` $\rightarrow$ `Investigator (RCA)` $\rightarrow$ `Architect` $\rightarrow$ `Reviewer` $\rightarrow$ `Custodian` $\rightarrow$ `Auditor` | **Architect-to-Investigator Delegation**: When encountering unexpected side-effects or mysterious test breaks during macro refactoring, `agyis_architect` pauses and delegates RCA to `agyis_investigator` instead of guess-editing. | `scratch/reproduce_*.py` + `rca_report.md` | PreInvocation locked DB handling |
| **G. Multi-Track Parallel Research / Landscape Mapping** | `agyis_coordinator` | `Coordinator` $\rightarrow$ Fan-out parallel `agyis_planner` / `agyis_investigator` $\rightarrow$ `Coordinator Synthesis` | **Context Preservation (ADR-025)**: Independent research tracks run in parallel contexts without cross-contamination. Results chiseled into persistent markdown. | `research_synthesis.md` / `track_*.md` | Epic Research Kickoff (Steps 5–17: 4 parallel research tracks) |
| **H. Cleanroom Specification Audit & Gap Ledger** | `agyis_investigator` | `Investigator` (Cleanroom Auditor) $\rightarrow$ `Coordinator` $\rightarrow$ `Builder` / `Swarm` | **Zero Production Mutation**: Evaluates baseline revision line-by-line against formal ACs. Documents gaps in `COMPLETION_LEDGER.md`. | `COMPLETION_LEDGER.md` | Issue #83 Route C Baseline Audit (Step 2488) |
| **I. Cross-Branch Golden Merge & Reconciliation** | `agyis_architect` | `Architect` (Synthesizer) $\rightarrow$ `Reviewer` $\rightarrow$ `Custodian` $\rightarrow$ `Auditor` | **Hermetic Worktree Isolation**: Reconciles divergent branches in dedicated worktree (`agyis-golden-merge`). Runs cross-test matrix. | Golden commit on unified feature branch | Epic #51 Phase 3.1 Route A vs Route B Golden Merge (Steps 1505 & 1603) |
| **J. Out-of-Band Victory Certification Council** | `agyis_auditor` + `agyis_reviewer` | `Auditor` (Hermetic Benchmarks) + `Reviewer` (8 Rules) $\rightarrow$ Dual Sign-Off | **Dual-Auditor Gate**: Never trust in-band self-certification. Independent auditors evaluate clean committed revision on HEAD. | `victory_audit_report.md` | Route A, B, and C Victory Audits (Steps 993, 2106, 3634, 3781) |
| **K. Milestone Governance & GitHub Issue Curation** | `agyis_custodian` | `Flight Director` / `Coordinator` $\rightarrow$ `Custodian` (Issue Formulation & Epic Sync via `gh` CLI) | **Zero Repository Document Pollution (AC5)**: Strictly zero scratch or progress notes in git tree; deterministic CLI execution; formal parent Epic checklist and comment updates verified via `gh issue view`. | GitHub Issues + Parent Epic Tracking Comment | Phase 3.3 GitHub Issue Harmonizer (Step 2095: Created #83, #84, #85 and synced Epic #51) |
| **L. Adversarial Fuzzing & Stress Hardening Battery** | `agyis_builder` / `agyis_investigator` | `Investigator` (Fuzzing Vectors) $\rightarrow$ `Builder` (Adversarial Tests) $\rightarrow$ `Reviewer` $\rightarrow$ `Custodian` $\rightarrow$ `Auditor` | **Zero Error Swallowing & Sub-Second SLA**: Stress tests (concurrency lock timeout $\le 0.5$s, schema corruption, rapid token bursts, stdin binary stream noise) must execute cleanly in sub-second latency and fail-open. | `tests/test_*_adversarial.py` | Route C Carrier-Grade Hardening (Step 2990: 4 adversarial hardening vectors) |

---

## Pillar 3: Dual-Plane Communication Contract

Communication in Track C is partitioned into two orthogonal, non-interfering planes: the **Human-in-the-Loop Operator Channel (Plane 1)** and the **Machine/Agent Communication Channel (Plane 2)**.

```mermaid
flowchart LR
    subgraph Plane1["Plane 1: Human-in-the-Loop Operator Channel"]
        USER["Human Software Architect"] <-->|"Conversational Markdown, Tables, Mermaid, Plans"| FD["Cockpit Flight Director"]
    end

    subgraph Plane2["Plane 2: Machine/Agent Private Channel"]
        FD <-->|"send_message(Recipient, psl_stage_transition_payload.json)"| COORD["agyis_coordinator"]
        COORD <-->|"Typed Stage Payloads & Defect Ledgers"| WORKERS["Specialist Workers<br/>(Investigator, Planner, Builder, Hammer, Custodian, Auditor)"]
    end
```

### 3.1 Plane 1: Human-in-the-Loop Operator Channel
1. **Concise Presentation**: The Flight Director communicates with the operator using clean markdown, structured comparison tables, and Mermaid flowcharts. Dense code dumps and raw terminal logs are strictly prohibited.
2. **Artifact-First Proposals (Rule 5 & ADR-012)**: Architectural proposals, milestone decompositions, and multi-file modifications must never be proposed as raw conversational chat text. They must immediately crystallize into an interactive `implementation_plan.md` artifact.
3. **Dynamic Sliding Aperture**:
   - **High Resolution**: Immediate active milestone (exact file declarations, unit tests, verification commands).
   - **Medium Resolution**: Near-future milestones (macro architectural boundaries; zero speculative code).
   - **Low Resolution**: Far-future vision and long-term roadmap.
4. **Proactive Confirmation Gates (Rule 6)**: The Flight Director must halt and request explicit operator confirmation before executing irreversible or destructive operations:
   - Git branch resets (`git reset --hard`), force pushes, or branch deletions.
   - Deletion of non-temporary workspace files.
   - Host service reboots or container system prunes.
5. **Anti-Thrashing Rule**: If any tool invocation, build step, or command fails twice consecutively, the Flight Director must stop immediately, state the error concisely, and present concrete options to the operator.

### 3.2 Plane 2: Machine/Agent Communication Channel
1. **The Subagent Privacy Invariant**: Text generated outside `send_message` by a subagent is **never** relayed to the parent orchestrator's context. Subagents must transmit all findings, test results, diff summaries, and handoffs via `send_message`.
2. **The Cockpit Demarcation Invariant**: The Cockpit Flight Director is the sole agent authorized to address the human operator in raw chat turns. Subagents (`agyis_builder`, `agyis_reviewer`, `agyis_auditor`) must never break encapsulation to query the user directly unless an explicit `ask_question` tool gate is authorized in their manifest.
3. **Strict Reactive Wait Invariant (Rule 4 & ADR-032)**:
   - When the Flight Director or Coordinator dispatches an asynchronous background task (`run_command` with large `WaitMsBeforeAsync`), subagent invocation (`invoke_subagent`), or timer (`schedule`), it must emit a single concise progress notification to the operator and **IMMEDIATELY STOP CALLING TOOLS**.
   - **Zero Polling Loops**: Calling `manage_task(Action='status')`, `manage_subagents(Action='list')`, or running `tail -f`, `cat`, `grep`, or `view_file` on `.system_generated/tasks/*.log` in consecutive turns is **STRICTLY PROHIBITED**.
   - Resumption is reactive: the Antigravity platform automatically wakes the agent when the task terminates or when a subagent calls `send_message`.

### 3.3 Typed Stage Transition Payload (`psl_stage_transition_payload.json`)

All stage handoffs along the subagent ladder must conform to the following formal JSON schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "AgyisStageTransitionPayload",
  "type": "object",
  "required": [
    "protocol_version",
    "task_id",
    "phase",
    "stage",
    "status",
    "sender_role",
    "next_recommended_stage",
    "git_commit_hash",
    "diff_summary",
    "verification",
    "artifacts"
  ],
  "properties": {
    "protocol_version": { "type": "string", "enum": ["2026.1"] },
    "task_id": { "type": "string", "description": "Unique identifier (e.g. ISSUE-83, TASK-P6.1)" },
    "phase": { "type": "string", "description": "Current phase (e.g. Phase 6: Cockpit Director Living Contract)" },
    "stage": {
      "type": "string",
      "enum": ["INVESTIGATION", "PLANNING", "EXECUTION", "CODE_REVIEW", "GIT_CUSTODY", "QA_AUDIT", "PROMOTION"]
    },
    "status": {
      "type": "string",
      "enum": ["PASS", "REJECT", "FAIL", "BLOCKED", "COMPLETE"]
    },
    "sender_role": {
      "type": "string",
      "enum": [
        "agyis_coordinator", "agyis_planner", "agyis_investigator",
        "agyis_builder", "agyis_reviewer", "agyis_custodian",
        "agyis_auditor", "agyis_architect", "cockpit_director"
      ]
    },
    "next_recommended_stage": {
      "type": "string",
      "enum": ["INVESTIGATION", "PLANNING", "EXECUTION", "CODE_REVIEW", "GIT_CUSTODY", "QA_AUDIT", "PROMOTION", "HALT_OPERATOR_INTERVENTION"]
    },
    "git_commit_hash": { "type": "string" },
    "diff_summary": {
      "type": "object",
      "required": ["modified_files", "added_lines", "deleted_lines", "contiguous_chunks_count"],
      "properties": {
        "modified_files": { "type": "array", "items": { "type": "string" } },
        "added_lines": { "type": "integer", "minimum": 0 },
        "deleted_lines": { "type": "integer", "minimum": 0 },
        "contiguous_chunks_count": { "type": "integer", "minimum": 0 }
      }
    },
    "verification": {
      "type": "object",
      "required": ["command", "exit_code", "total_tests", "passed_tests", "failed_tests", "benchmark_latency_s"],
      "properties": {
        "command": { "type": "string" },
        "exit_code": { "type": "integer" },
        "total_tests": { "type": "integer", "minimum": 0 },
        "passed_tests": { "type": "integer", "minimum": 0 },
        "failed_tests": { "type": "integer", "minimum": 0 },
        "benchmark_latency_s": { "type": "number", "minimum": 0.0 }
      }
    },
    "artifacts": {
      "type": "object",
      "required": ["plan_path", "reproduction_script", "report_path"],
      "properties": {
        "plan_path": { "type": ["string", "null"] },
        "reproduction_script": { "type": ["string", "null"] },
        "report_path": { "type": ["string", "null"] }
      }
    },
    "defect_ledger": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["defect_id", "file_path", "line_range", "violated_rule", "description", "remediation"],
        "properties": {
          "defect_id": { "type": "string" },
          "file_path": { "type": "string" },
          "line_range": { "type": "string" },
          "violated_rule": { "type": "string" },
          "description": { "type": "string" },
          "remediation": { "type": "string" }
        }
      }
    }
  }
}
```

---

## Pillar 4: Compaction Lifecycle & Native Succession Protocol (ADR-031 / Issue #77)

Context compaction is an inevitable reality in long-horizon engineering campaigns. Rather than treating compaction as an unpredictable amnesic trauma, Track C codifies a deterministic **Compaction Lifecycle & Native Succession Protocol**.

```mermaid
stateDiagram-v2
    [*] --> HealthyZone: Session Initialized
    HealthyZone --> AmberZone: Tokens >= 180k
    AmberZone --> CompactionImminent: Tokens >= 230k / Spawns >= 16
    CompactionImminent --> CheckpointAssembly: PreInvocation Hook Injects Advisory
    CheckpointAssembly --> CognitiveCompression: Lock-Free proto_compaction_checkpoint.py (<30ms)
    CognitiveCompression --> CheckpointStep: Platform Model Summary (<summary>...</summary>)
    CheckpointStep --> SuccessorWakeup: Platform Injects Resumption Banner (# Resuming...)
    SuccessorWakeup --> HealthyZone: Autonomous Verification & Task Resumption
```

### 4.1 Context Proximity Thresholds
1. **🟢 Healthy Zone (<180,000 tokens)**:
   - Normal autonomous operations.
   - Standard milestone decomposition and subagent dispatches.
   - Regular aperture updates in `project_ledger.md`.
2. **🟡 Amber Zone (180,000 – 229,999 tokens)**:
   - Pre-compaction awareness mode.
   - The Flight Director must avoid launching sprawling, multi-file refactoring milestones.
   - Complete active stages; instruct the Hammer and Custodian to commit in-flight diffs to git on HEAD.
3. **🔴 Compaction Imminent (>= 230,000 tokens or Spawns >= 16)**:
   - The `pre_invocation_hook.py` detects token proximity via protobuf varint step accounting and injects the ephemeral **Compaction Imminent Advisory**.
   - Mandatory materialization of working memory: the Flight Director or Coordinator executes `proto_compaction_checkpoint.py` to assemble `.agents/artifacts/compaction_checkpoint.md`.
   - The Flight Director prompts the operator for a clean `/compact` slash command or invokes horizontal succession:
     `invoke_subagent(TypeName="self", Workspace="inherit")`.

### 4.2 Compaction Mechanics in the Antigravity Engine
Reverse engineering of the compiled binary (`/usr/bin/agy` and `/opt/Antigravity/resources/bin/language_server`, CL `951519500`) revealed that compaction operates as a two-phase pipeline:

1. **Phase 1: Model Cognitive Compression (Zero Tool Calls)**:
   - The language server executes `CheckpointHandler` using `CHECKPOINT_STRATEGY_SAME_MODEL`.
   - The model is prompted with a structured 6-part schema:
     1. Task Overview (core requests, constraints).
     2. Progress (completed files, tool outputs, artifacts).
     3. Key Findings (decisions made, errors resolved, **abandoned approaches**).
     4. Active Context (working hypotheses, active sessions).
     5. Next Steps (prioritized next actions, blockers).
     6. Commitments & Constraints (explicit promises, styling rules).
   - The model emits a dense summary wrapped in `<summary>...</summary>`. **No tool calls are executed during this phase.**
2. **Phase 2: Platform Checkpoint Generation (`CortexStepCheckpoint`)**:
   - The platform serializes the summary, diff metadata, and artifact hashes into a synthetic step (`step_type = 4`) stored in SQLite (`~/.gemini/antigravity/conversations/<id>.db`).
   - The platform injects the resumption banner:
     `# Resuming from a compaction... <CONTEXT_SUMMARY>...</CONTEXT_SUMMARY>`.

### 4.3 Lock-Free Pre-Compaction Checkpoint Assembly (`proto_compaction_checkpoint.py`)
To prevent data loss, the Flight Director materializes ground truth in `<30ms` latency via `scratch/proto_compaction_checkpoint.py`:
- **Git State**: Branch, short HEAD commit, clean/dirty porcelain status, diff stat.
- **Subagent Liveness**: Active conversation IDs, step counts, token counts, and health zones (`HEALTHY`, `AMBER`, `RED_ALERT`).
- **Artifact Catalog**: Active plans, reports, and ledgers in `.agents/artifacts/` with sizes and links.
- **Plan Status**: Total tasks, completed tasks, in-progress phase, and immediate next actionable step.
- Writes to `.agents/artifacts/compaction_checkpoint_<epoch>.md` and updates the latest pointer `.agents/artifacts/compaction_checkpoint_latest.md`.

### 4.4 Autonomous Post-Compaction Continuation Directive
When waking up in a compacted session or successor context, the agent is bound by the **Zero Operator Prompting Rule**:
- **FORBIDDEN**: Asking the operator *"What was I doing?"*, *"Can you remind me of our goal?"*, or *"Should I proceed?"*.
- **MANDATORY WAKE-UP CHECKLIST**:
  1. [ ] Run `git status` and `git diff --stat` to verify in-flight modifications survived intact.
  2. [ ] Read `.agents/artifacts/compaction_checkpoint_latest.md` and `implementation_plan.md`.
  3. [ ] Run `./agyis test` (or `python3 -m harness.cli test`) to assert baseline verification health.
  4. [ ] Autonomously resume execution of the current pending phase!

---

## Pillar 5: 3-Tier Storage Hierarchy & Zero Repo Document Pollution (AC5)

To guarantee that git history represents strictly deployable production assets while providing durable storage for architecture plans and ephemeral sandboxes for reproduction scripts, Track C enforces a strict **3-Tier Storage Hierarchy**:

```mermaid
flowchart TD
    subgraph Tier1["Tier 1: Living Artifacts (Durable, Cross-Compaction)"]
        A1[".agents/artifacts/*.md<br/>(Master plans, delivery reports, architectural specifications)"]
        A2["<appDataDir>/brain/<conversation-id>/*.md<br/>(Interactive plans, operator ledgers, RCA reports)"]
    end

    subgraph Tier2["Tier 2: Scratch Directory (Ephemeral, Non-Committed)"]
        S1["<appDataDir>/brain/<conversation-id>/scratch/*<br/>(Reproduction scripts, fuzzers, trace logs)"]
        S2["scratch/* or /tmp/*<br/>(Temporary output dumps, intermediate diffs)"]
    end

    subgraph Tier3["Tier 3: Git Working Tree (Strictly Production Assets)"]
        G1["harness/* (Distributable plugin, hooks, CLI)"]
        G2["tests/* (Automated unit and contract test suites)"]
        G3["docs/* (Cleanroom specs, public documentation, ADRs)"]
    end

    Tier2 -.->|"Filtered out by Custodian & .gitignore"| Tier3
    Tier1 -.->|"Referenced via links; never committed as code debris"| Tier3
```

### 5.1 The 3-Tier Storage Matrix

| Dimension | Tier 1: Living Artifacts | Tier 2: Scratch Directory | Tier 3: Git Working Tree |
| :--- | :--- | :--- | :--- |
| **Physical Paths** | `.agents/artifacts/`<br>`<appDataDir>/brain/<id>/` | `<appDataDir>/brain/<id>/scratch/`<br>`scratch/` | `harness/`, `tests/`, `docs/`, `pipeline/` |
| **Persistence** | Durable across compaction, session resets, and agent lifecycles. | Ephemeral to the active mission or bug investigation. | Versioned permanently in git commit history. |
| **Typical Contents** | `implementation_plan.md`, `rca_report.md`, `project_ledger.md`. | `reproduce_issue.py`, `fuzz_payload.bin`, `trace.log`. | Production Python modules, unit test files, docs. |
| **Git Commit Rule** | Read-only reference or versioned documentation. | **STRICTLY FORBIDDEN IN GIT COMMITS**. | The only files staged by `agyis_custodian`. |
| **Tool Access** | `write_to_file`, `replace_file_content`, `view_file`. | `write_to_file`, `run_command` (Python/bash runner). | `replace_file_content` (surgical), `view_file`. |
| **Anti-Drift Guard** | Exempt from plan matching restrictions. | Exempt from plan matching restrictions. | Strictly checked against `implementation_plan.md`. |

### 5.2 Acceptance Criterion 5 (AC5): Zero Repository Document Pollution
> **AC5 Mandate**: The git repository working tree and commit log must remain 100% free of temporary progress notes, ephemeral reproduction scripts, scratch markers, WIP scratchpads, or conversational compaction summaries.

#### Mechanical Enforcement Rules:
1. **The Custodian Staging Filter**: `agyis_custodian` must run `git status --porcelain` prior to staging. Any path matching `scratch/*`, `tmp/*`, `*.tmp`, `*.log`, `*.db`, or non-whitelisted markdown progress markers is rejected. Blind `git add .` or `git add -A` is an immediate fireable failure of the Custodian invariant.
2. **Anti-Drift File Boundary**: The `anti_drift_hook` deterministically blocks writes to undeclared code files while permitting edits to Tier 1 and Tier 2 paths. This guides models to place experimental code strictly into `scratch/`.
3. **Spec-Dirty vs. Code-Dirty Segregation**: Modifying an artifact or specification in Tier 1 marks `spec_dirty = True` in verification state, which requires specification or schema verification, but does NOT trigger synthetic unit test obligations on non-existent code.

---

## Pillar 6: Operational Flight Checklists & Emergency Escalation Runbook

### 6.1 Flight Director Golden Path Pairing Checklist

```markdown
### 🛫 Flight Director Pairing Sequence

1. [ ] **Session Initialization & Baseline Audit**:
   - Check current git status (`git status --short`).
   - Check test suite baseline (`python3 -m harness.cli test`). Confirm exit code 0.
   - Inspect active token consumption (<180k healthy zone).

2. [ ] **Requirements Crystallization & Classification**:
   - Listen to operator objective.
   - Classify into one of the 12 Canonical Autonomous Routing Workflows (Workflows A–L).
   - If bug or regression -> Route to `agyis_investigator` for scratch reproduction script.
   - If new feature or multi-file milestone -> Route to `agyis_planner` for `implementation_plan.md`.

3. [ ] **Plan Lock-In & Operator Confirmation**:
   - Author interactive `implementation_plan.md` artifact (`RequestFeedback: true`).
   - Confirm target file declarations (`[MODIFY]`, `[NEW]`, `[DELETE]`).
   - Await explicit operator confirmation ("Proceed" / "Approved").

4. [ ] **Subagent Ladder Dispatch & Reactive Wait**:
   - Dispatch stage specialist (`invoke_subagent`).
   - Emit a concise progress notification to the operator.
   - STOP CALLING TOOLS. Await reactive wakeup. Zero polling loops!

5. [ ] **Dual-Auditor Gate Enforcement**:
   - Verify that Stage 3 Hammer (`agyis_reviewer`) reviewed the diff against the 8 Empirical Rules with verdict `PASS`.
   - Verify that Stage 4 Custodian (`agyis_custodian`) verified DRY deduplication and committed atomically on HEAD.
   - Verify that Stage 5 Victory Auditor (`agyis_auditor`) executed `./agyis test` on HEAD with exit code 0 in sub-second benchmark latency (<1.0s).

6. [ ] **Milestone Promotion & Horizon Compaction**:
   - Update `project_ledger.md` (<50 lines compaction).
   - Update roadmap checkboxes.
   - Present concise completion summary to operator with clickable diff links.
```

### 6.2 Emergency Escalation Matrix

| Trigger Event | Diagnostic Indicator | Immediate Flight Director Action | Escalation Channel |
| :--- | :--- | :--- | :--- |
| **Command Failure Thrash** | Same command fails $\ge 2$ times | Halt execution immediately. Emit concise error diagnosis. Present 2–3 concrete remediation options. | Operator Chat Turn (Plane 1) |
| **Destructive Command Gate** | File deletion, branch force-push, node restart | Block command. Present explicit confirmation prompt with blast radius description. | Operator Confirmation Gate |
| **Context Cliff Alarm** | Tokens $\ge 230,000$ or Spawns $\ge 16$ | Execute `proto_compaction_checkpoint.py`. Materialize state in `.agents/artifacts/`. Prompt operator for `/compact`. | PreInvocation Advisory & Chat |
| **Subagent Red Alert** | Subagent tokens $> 80,000$ | Retire subagent. Spawn fresh successor with compacted task payload. | Private Inter-Agent (Plane 2) |
| **Hardware Mesh Offline** | SSH ControlMaster socket timeout | Revert from remote swarm to local hermetic worktree. Log mesh alert. | Operator Chat Turn (Plane 1) |

---

## Pillar 7: Verification & Living Contract Invariants Summary

To ensure this document remains the authoritative source of truth, all Agyis harness agents, hooks, and subagent ladders are bound by the following inviolable principles:

1. **Sub-Second Benchmark Invariant (Rule 1 & ADR-015)**:
   - All unit test suites and hook runners must execute within sub-second benchmark latency (<1.0s, typically <0.20s). Verification must be fast, hermetic, and panic-free.
2. **Surgical Contiguous Edits Invariant (Rule 3)**:
   - All code edits must be executed via single contiguous block replacements (`replace_file_content`). Whole-file overwriting is strictly prohibited.
3. **Strict Reactive Wait Invariant (Rule 4 & ADR-032)**:
   - Polling loops on background tasks or subagent logs are banned. Stop tool execution after dispatch and await platform reactive wakeup.
4. **Artifact-First Planning Invariant (Rule 5 & ADR-012)**:
   - No multi-file or architectural changes may be executed without an approved `implementation_plan.md` artifact.
5. **Zero Repository Document Pollution (AC5)**:
   - Git trees and commits must remain 100% free of scratch scripts, temporary notes, or compaction dumps.
6. **Dual-Auditor Gate (Rule 8)**:
   - Independent Stage 3 Hammer review and Stage 5 Victory Auditor certification are mandatory before any milestone is promoted.

---
<!-- End of Document PSL-SPEC-2026-COCKPIT-DIRECTOR-001 -->
