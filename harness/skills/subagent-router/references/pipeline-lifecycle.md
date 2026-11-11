<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Subagent Router: 6-Stage Pipeline Lifecycle & State Machine Details

Detailed flow diagram and stage gate contracts for [SKILL.md](../SKILL.md).

## 1. Visual 6-Stage Execution Flow

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
│ - Local self-verification via targeted component tests (<1.0s benchmark). │                         │
│ - Produces diff summary and local test pass.                            │                         │
└────────────────────────────────────┬────────────────────────────────────┘                         │
                                     │ (Execution Complete OR Remedy Complete)                      │
                                     ▼                                                              │
┌─────────────────────────────────────────────────────────────────────────┐                         │
│ STAGE 3: CODE REVIEW & QUALITY AUDIT (`agyis_reviewer` - The Hammer)    │                         │
│ - Independent agent audits diff against the 11 Universal Invariants.    │                         │
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
│ - Runs `agyis test` (~65s full suite) + <1.0s component benchmarks.     │                         │
│ - Asserts exit code 0 across all hermetic suites.                       │                         │
└──────────────────┬───────────────────────────────┘                                                │
                   │                                                                                │
         ┌─────────┴─────────┐                                                                      │
         │ (Passed QA Audit) │ (QA/Audit Failed)       ─────────────────────────────────────────────┘
         │                   │                                 (MANDATORY: Return to Builder/Investigator,
         ▼                   │                                 THEN through Hammer!)
┌────────────────────────────┴────────────────────────────────────────────┐
│ STAGE 6: PHASE ARCHIVAL & PROMOTION (`cockpit-director.md` / `agyis_coordinator`) │
│ - Archives milestone plan into `.agents/artifacts/phase_X_delivery.md`. │
│ - Records milestone completion in `docs/taxonomy/project-ledger.md`.     │
│ - Subagents for completed phase are formally retired.                   │
│ - Presents Phase X+1 Implementation Plan to user.                       │
└─────────────────────────────────────────────────────────────────────────┘
```

## 2. Custodian Rejection & Anti-Bypass Guarantees

- **Anti-Bypass Formula**: $\text{Auditor FAIL} \longrightarrow \text{Builder (Remedy)} \longrightarrow \mathbf{Reviewer\ (The\ Hammer\ Re\text{-}Review)} \longrightarrow \mathbf{Custodian\ (Commit\ Gate)} \longrightarrow \text{Auditor (QA)}$
- **Custodian Rejection Formula**: $\text{Custodian REJECT} \longrightarrow \mathbf{Builder\ (Remediation)} \longrightarrow \mathbf{Reviewer\ (The\ Hammer\ Re\text{-}Review)} \longrightarrow \mathbf{Custodian\ (Re\text{-}Audit)}$
- Under no circumstances may an Executioner remedy or architectural remediation bypass Hammer review or Stage 4 Custodian commit sealing before Stage 5 Auditor verification.
