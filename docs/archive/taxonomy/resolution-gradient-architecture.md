<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# 🔭 The Resolution Gradient Architecture: Dynamic Aperture & Retroactive Compaction

**Project**: PSL Harness for Google Antigravity™ (`psl-agy-harness`)  
**Specification**: Version 1.1 — Dynamic Horizon Compaction Protocol  
**Publisher**: Purrfect Software Limited (PSL)  

---

## 1. The Dynamic Aperture Principle

The standard Resolution Gradient divides future and present work into three progressive horizons. However, in long-horizon engineering, **uncompacted history is just as toxic to context windows as premature future over-specification**. 

Without maintenance, past completed steps accumulate voluminous implementation logs, debug traces, intermediate PR diffs, and conversational churn, causing the dreaded **200+ step context cliff**.

The PSL Resolution Gradient operates as a **Dynamic Sliding Aperture**:

```text
 ┌───────────────────┬────────────────────┬──────────────────────┬──────────────────────┐
 │    HORIZON 0      │     HORIZON 1      │      HORIZON 2       │      HORIZON 3       │
 │ Past (Compacted)  │ Present (High-Res) │ Intermediate (Mid)   │ Far Horizon (Low)    │
 ├───────────────────┼────────────────────┼──────────────────────┼──────────────────────┤
 │ • Key Decisions   │ • Active Sprint    │ • Architectural      │ • Strategic Vision   │
 │   (ADRs)          │ • Executable Tests │   Enablers           │ • Ecosystem          │
 │ • Schema Contracts│ • Line-level Types │ • Macro Milestones   │   Connectors         │
 │ • Verification    │ • Strict Boundaries│ • Domain Interfaces  │ • Protocol           │
 │   Proofs          │   (Active turn)    │   (Next sprint)      │   Evolutions         │
 └───────────────────┴────────────────────┴──────────────────────┴──────────────────────┘
         ▲                    ▲                       ▲
         │                    │                       │
   COMPACTION FENCE     PROMOTION GATE          PROMOTION GATE
   (Noise Fades Out)    (Empirical Proof)       (Telemetry Trigger)
```

---

## 2. Retroactive Horizon Compaction (H1 ➔ H0)

As the development needle moves forward, old completed horizons **must mechanically shrink**. 

### What Fades Out (Noise Pruning):
* Ephemeral implementation debates and multi-turn debug transcripts.
* Temporary scaffolding scripts, scratch logs, and intermediate test runner outputs.
* Granular function-level refactor narratives that are already captured in git history.

### What Remains Permanent (Horizon 0 Core):
1. **Architectural Decision Records (ADRs)**: The *why* behind non-obvious design choices.
2. **Schema & Interface Contracts**: Permanent API, database, or socket invariants.
3. **Empirical Verification Proofs**: Key benchmark numbers, baseline telemetry, and passing test suites.
4. **Permanent Invariant Rules**: New additions to `AGENTS.md` discovered during execution.

---

## 3. Compaction Lifecycle Rules

1. **The 50-Line Ledger Constraint**:
   - Each completed phase or milestone must be condensed into a canonical summary entry under **50 lines**.
   - Detailed operational walkthroughs live in historical artifact files (`docs/archive/`), never in active agent context.

2. **Automated Horizon Rolling**:
   - When Phase $N$ completes and Phase $N+1$ becomes active:
     - Phase $N$ artifacts are archived to storage.
     - Phase $N$ key outcomes are appended to the permanent ledger (`docs/taxonomy/project-ledger.md`).
     - Active context resets its high-resolution budget for Phase $N+1$.

3. **Context Lifetime Invariant**:
   - An agent working on Phase $N+1$ is injected with:
     - **Full High-Res**: Phase $N+1$ active tasks and tests.
     - **Compacted H0**: Permanent architectural ledger and invariant rules.
     - **Zero Ephemeral Noise**: Zero uncompacted transcripts or scratch dumps from Phase $N$.
