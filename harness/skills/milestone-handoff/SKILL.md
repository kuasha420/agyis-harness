---
name: milestone-handoff
description: >-
  Standardized protocol for completing, compacting, and handing off engineering milestones.
  Use when completing a milestone or phase, updating the project ledger and roadmap,
  verifying test suites, and instructing the operator to reset into a fresh session.
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Milestone Handoff & Retroactive Horizon Compaction Protocol

This skill codifies the verified milestone handoff procedure that prevents cognitive drift, attention sink collapse, and context saturation across long engineering sessions.

---

## 1. When to Trigger
Trigger this protocol immediately upon:
1. All proposed code changes for the current milestone being implemented.
2. All unit and contract tests passing with 100% coverage.
3. The session approaching or exceeding **180k–230k tokens** (amber/red thresholds of the 256k window) or **45–50 steps** (step interrupt horizon).

---

## 2. Step-by-Step Execution Sequence

### Step 1: Clean-Room Automated Verification
Before modifying documentation or claiming completion, execute the project native test suite and verify clean exit code 0:
```bash
# Execute native test suite (e.g. agyis test, pnpm test, pytest, cargo test)
agyis test
```
*Rule*: If any test fails, STOP. Do not proceed to handoff until all tests pass.

### Step 1.5: Architectural Fitness & Packaging Verification
Execute the native Architectural Fitness Function audit to ensure the milestone introduces zero structural regressions or boundary defects:
```bash
# Execute Architectural Fitness Function audit
agyis audit aff
```
*Verification Mandate*:
1. **Zero Boundary Breaches**: Verify layer bifurcation (e.g. `harness/` never imports `pipeline/`, cleanroom never imports dirtyroom).
2. **Zero Cycles**: Verify module import graphs are strictly acyclic (DAG).
3. **Decoupled Assets**: Verify non-native assets (HTML/CSS/JS/SQL/templates) are decoupled into dedicated `assets/` directories and declared in packaging manifests.
4. **Bounded Caches**: Verify in-memory state caches have capacity bounds, LRU eviction, or TTL limits.
*Rule*: If `agyis audit aff` returns FAIL or identifies newly introduced critical architectural defects, resolve them before proceeding to ledger compaction or commit.

### Step 2: Retroactive Horizon Compaction (Project Ledger)
Record the completed phase in the project ledger (e.g. `docs/taxonomy/project-ledger.md` or repository-configured ledger path):
- Keep the entry **strictly under 50 lines**.
- Record only:
  - Permanent Architectural Decisions (ADRs) with rationale.
  - Verified baseline empirical metrics (e.g. test counts, execution latency).
  - List of committed reference assets.
- Do NOT record transient scratch logs, full error stack traces, or multi-turn transcripts (these fade into git history).

### Step 3: Master Roadmap Update (Roadmap / Milestones)
- Update the milestone status in `roadmap.md` (or project roadmap/tracking document, e.g. `ROADMAP.md` or `PROJECT.md`).
- Realign the next upcoming milestones at **Medium Resolution** (macro milestones and architectural boundaries; do not write speculative code).

### Step 4: Walkthrough Artifact Generation
- Create or update `<artifactDir>/walkthrough.md` summarizing:
  - Exact components implemented.
  - Verification test outputs and commands executed.
  - Key architectural decisions made.

### Step 5: Git Clean Commit & Push
- Verify `git status` and `git diff`.
- Stage only relevant files:
  ```bash
  git add <files>
  git commit -m "feat(<scope>): <concise summary>" -m "- <bullet 1>" -m "- <bullet 2>"
  git push origin main
  ```
- Ensure working tree is completely clean.

### Step 6: Session Reset Recommendation
Because attention degradation and compaction pressure increase once a session enters the 180k/230k context runway (of the 256k window) or crosses 45–50 steps, always recommend that the operator reset into a fresh session for the next milestone:
> *"Milestone completed and committed. All tests pass. Working tree clean. To maintain maximum reasoning aperture and prevent cognitive degradation, please reset into a fresh conversation turn for the next milestone."*
