---
name: code-review
description: >-
  Delta-focused code review and comment resolution protocol.
  Use when reviewing code changes, addressing pull request review comments,
  or inspecting git diffs to prevent full-repository re-reading loops.
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Delta-Focused Code Review & Feedback Protocol

This skill codifies the delta-focused review workflow derived from high-performing repositories in our empirical dataset (such as `purrmission` and `sunshine-physio`), where focused line-level reviews reduced human interventions by 10x compared to whole-repo re-reading.

---

## 1. Core Principles

1. **Delta Focus Over Full Re-Reads**:
   - When reviewing changes or addressing PR feedback, inspect ONLY the changed files and specific modified line ranges (`git diff -U3`).
   - NEVER call `view_file` on entire 1,000-line files when review comments target a 5-line function.
2. **Review Delay Fence**:
   - In active PR cycles, wait for automated test runners and linters to complete before attempting fixes. Do not race against active CI pipelines.
3. **Surgical Contiguous Corrections**:
   - Use `replace_file_content` to apply focused contiguous edits addressing specific feedback items.
4. **Mandatory Post-Fix Verification**:
   - After addressing review comments, immediately run the project test suite (`agyis test`, `pnpm test`, `pytest`, etc.) to prove the fix introduces zero regressions.
5. **Delta-Aware Macro Smell Sensing**:
   - While maintaining strict delta focus on modified lines (`git diff -U3`), reviewers must actively evaluate whether an incoming diff compounds existing structural debt or introduces macro architectural smells:
     * **Foreign Language Monoliths**: Does the diff append more inline HTML/CSS/JS/SQL strings to an already monolithic string template instead of extracting to `assets/`?
     * **Cross-Boundary Coupling**: Does the diff introduce illegal cross-layer or cross-package imports (e.g. core distributable code importing experimental pipelines, or cleanroom leaking dirtyroom)?
     * **Unbounded State Caching**: Does the diff introduce dictionary or collection caches without explicit capacity bounds, LRU eviction, or TTL limits?
     * **Compounding Complexity**: Does the diff add complexity to an existing God Component (>2,000 lines) without submodule decomposition?
   - If any macro smell is compounded, Hammer flags the line in the defect ledger with concrete refactoring recommendations before approving the diff.

---

## 2. Review Invocations

### Inspect Current Workspace Diffs
```bash
# View summary of modified files
git status -s

# Inspect compact unified diff of unstaged changes
git diff -U3

# Inspect compact unified diff of staged changes
git diff --cached -U3
```

### Review Resolution Checklist
1. Identify exact line numbers and variables referenced in the review comment.
2. View targeted line slice using `view_file(StartLine=X, EndLine=Y)`.
3. Apply surgical replacement via `replace_file_content`.
4. Run project test suite: `agyis test` (or native test runner: `pnpm test`, `pytest`, `cargo test`).
5. Stage and commit specifically with: `fix(<component>): resolve review feedback on <target>`.
