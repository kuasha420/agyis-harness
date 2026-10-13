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
3. The session approaching or exceeding **35k–50k tokens** or **50 steps** (entering the Amber warning zone).

---

## 2. Step-by-Step Execution Sequence

### Step 1: Clean-Room Automated Verification
Before modifying documentation or claiming completion, execute the project test suite and verify clean exit code 0:
```bash
python3 -m harness.cli test
```
*Rule*: If any test fails, STOP. Do not proceed to handoff until all tests pass.

### Step 2: Retroactive Horizon Compaction (`docs/taxonomy/project-ledger.md`)
Record the completed phase in the permanent ledger:
- Keep the entry **strictly under 50 lines**.
- Record only:
  - Permanent Architectural Decisions (ADRs) with rationale.
  - Verified baseline empirical metrics (e.g. test counts, execution latency).
  - List of committed reference assets.
- Do NOT record transient scratch logs, full error stack traces, or multi-turn transcripts (these fade into git history).

### Step 3: Master Roadmap Update (`roadmap.md`)
- Update the milestone status in `roadmap.md` (e.g. from `IN PROGRESS` to `COMPLETED`).
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
Because attention degradation accelerates past 50k tokens (the 100k cliff), always recommend that the operator reset into a fresh session for the next milestone:
> *"Milestone completed and committed. All 43 tests pass. Working tree clean. To maintain maximum reasoning aperture and prevent cognitive degradation, please reset into a fresh conversation turn for the next milestone."*
