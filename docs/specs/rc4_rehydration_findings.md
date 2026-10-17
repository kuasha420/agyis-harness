<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Empirical Rehydration & Fleet Rebase Findings: Agyis Harness v1.0.0-rc4 Cohort Deployment

```
Document Status : Formal Specification & Empirical Input for v1.0.0-rc5
Document Version: 1.0.0
Author          : Flight Director CapCom & Specialist Architecture Fleet
Target Engines  : Agyis Harness v1.0.0-rc4 -> v1.0.0-rc5
Date of Sweep   : 2026-10-16 to 2026-10-17
Audited Repos   : 5 Repositories + 1 Auxiliary Clone across purrfectsoft and kuasha420
Pipeline Scope  : 16 Open PRs Rebased & Verified, 5 Default Branches Rehydrated
```

---

## 1. Executive Summary & Verification Master Table

Following the Phase 0 fleet audit, an immediate focused deployment of **Agyis Harness `v1.0.0-rc4`** was executed across the **5 highest-velocity repositories** in the Purrfect Software portfolio.

Across all 5 codebases, default branches were synchronized, rehydrated with canonical `rc4` rule blocks, cleansed of duplicate workspace skills via single-source delivery (`Issue #52`), and verified with native test suites. All **16 active open PRs**—including 3 hard-conflicting branches—were sequentially rebased, verified with 100% test pass rates, and confirmed as cleanly `MERGEABLE` on GitHub.

```
┌────────────────────────────────┬──────────────────────────────┬──────────┬─────────────────────────────┬───────────────────────────┐
│ Target Repository & Path       │ Architectural Archetype      │ Open PRs │ Native Verification Suites  │ Rebase & GitHub Status    │
├────────────────────────────────┼──────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────┤
│ sunshine-physio-universalapp   │ Next.js 15 + Expo / React    │ 6 of 6   │ 201 test files /            │ 🟢 6/6 Rebased &          │
│ (~/Dev/sunshine-physio-webapp) │ Native Universal Monorepo    │          │ 2,838 tests passed (vitest) │ MERGEABLE (PRs #55–#60)   │
├────────────────────────────────┼──────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────┤
│ kuasha420/knot-mesh            │ Python 3.12 + Bash/systemd   │ 5 of 5   │ 44 pytest + 5/5 integrity   │ 🟢 5/5 Rebased &          │
│ (~/Dev/knot-mesh)              │ Wayland Hardware Mesh Swarm  │          │ bash suites (exit code 0)   │ MERGEABLE (PRs #85, 87–90)│
├────────────────────────────────┼──────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────┤
│ purrfectsoft/purrfectcore-001  │ NestJS 11 + Prisma ORM       │ 2 of 2   │ 66 test suites /            │ 🟢 2/2 Rebased &          │
│ (~/Dev/purrfectcore-001)       │ Enterprise Backend Monolith  │          │ 1,068 tests passed (jest)   │ MERGEABLE (PRs #566, #268)│
├────────────────────────────────┼──────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────┤
│ purrfectsoft/psl-website       │ Next.js + Turborepo + tRPC   │ 2 of 2   │ pnpm build (58 static pages)│ 🟢 2/2 Rebased &          │
│ (~/Dev/psl-website)            │ Corporate Portal Monorepo    │          │ pnpm typecheck (0 errors)   │ MERGEABLE (PRs #57, #61)  │
├────────────────────────────────┼──────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────┤
│ purrfectsoft/mm-website        │ Next.js + Turborepo Client   │ 1 of 1   │ pnpm build (3 tasks OK)     │ 🟢 1/1 Rebased &          │
│ (~/Dev/mm-website)             │ Web Platform (46 issues)     │          │ pnpm typecheck (0 errors)   │ MERGEABLE (PR #406)       │
├────────────────────────────────┼──────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────┤
│ purrfectsoft/mm-website-2      │ Auxiliary Monorepo Clone     │ N/A      │ agyis doctor 9 OK,          │ 🟢 Synchronized to        │
│ (~/Dev/mm-website-2)           │ Duplicate Workspace Checkout │          │ legacy .agent/ eliminated   │ develop & Clean           │
└────────────────────────────────┴──────────────────────────────┴──────────┴─────────────────────────────┴───────────────────────────┘
```

---

## 2. Deep Forensic Rebase & Conflict Case Studies

### 2.1 Case Study 1: Enterprise Prisma Schema Divergence (`purrfectcore-001` PR #566)
- **Branch**: `chore/remove-prisma-comments` (author: `@smamun19`)
- **Initial State**: `DIRTY / CONFLICTING` against `develop`.
- **Anatomy of Conflict**:
  During the lifecycle of PR #566, the `develop` branch evolved rapidly with major domain refactors: the CareBridge therapy package architecture, advance receipt sequences, and patient credit transaction ledgers. PR #566 consisted of two sequential commits: first stripping all comments from all Prisma schema models, and then re-introducing high-signal docstrings.
- **Resolution Strategy**:
  The worker executed surgical AST and block-level reconciliation across 14 conflict regions in `rbac.prisma`, `finance.prisma`, and `hospital.prisma`:
  - Retained `develop`'s authoritative field definitions (`slotsReleasedAt`, `completedAt`, referral relations, `patientPackageId`, `cancellationCreditAmount`).
  - Integrated the author's high-signal docstrings on `CreditTransactionType`, `PatientCreditTransaction`, and `ServicePricing`.
- **Validation**: Full Jest test suite verified **66 suites passed, 1,068 tests passed** in 8.3s. PR updated to commit `b891823c` and marked `MERGEABLE`.

### 2.2 Case Study 2: 100% Conflict Density Resolution (`psl-website` PRs #57 & #61)
- **Initial State**: Both open PRs in `psl-website` were completely blocked on merge conflicts against `develop`.
- **Resolution Strategy**:
  1. **PR #57 (`fix/security-alert-and-editor-types`)**:
     - Merged `nodemailer` dependencies into `apps/web/package.json` alongside Next.js 15.5.27.
     - Harmonized tRPC settings persistence (`api.settings.set`) with the rich maintenance control card in `settings-view.tsx`.
     - Regenerated Prisma client to register the `UserDevice` model in `@prisma/client`.
     - Output: 57 static pages built cleanly; PR #57 marked `MERGEABLE` (`7d5e90b`).
  2. **PR #61 (`feat/back-office-ai-automation`)**:
     - Unified router registration in `apps/web/src/server/routers/_app.ts` with both `postsRouter` and `aiRouter`.
     - Remediated 8 strict ESLint/TypeScript errors (`@typescript-eslint/no-explicit-any`, missing timer cleanups in `ai/health/route.ts`).
     - Output: 58 static pages built cleanly; PR #61 marked `MERGEABLE` (`8bfc0fc`).

### 2.3 Case Study 3: Dead Code Pruning vs. Stale Unit Tests (`sunshine-physio` PR #56)
- **Initial State**: Rebase succeeded, but `vitest run` failed on `layout.test.tsx`.
- **Anatomy of Friction**:
  PR #56 intentionally pruned multi-branch dead code from `apps/web/src/app/(admin)/layout.tsx` (Issue #19). However, the pre-existing unit test in `layout.test.tsx` still asserted that the `branch-switcher-button` and `Branches` navigation links rendered when `enableMultiBranch: true`.
- **Resolution**:
  Updated the unit test to assert that neither `branch-switcher-button` nor `Branches` nav links are rendered (`toBeNull()`), maintaining strict alignment with the dead-code pruning specification. Commit amended (`155b7b2`), full test suite passed (198 files, 2,783 tests), and pushed with lease.

---

## 3. Top 8 Empirical Frictions & Hard Learnings

The rehydration and rebase sweep exposed 8 critical real-world friction patterns that directly dictate the design of `rc5`:

### 1. The Next.js Cross-Branch Type Cache Corruption
- **Phenomenon**: Switching between branches that define different route structures leaves stale declaration files in `.next/types/` (e.g. `maintenance/page.ts` missing after branch switch). Subsequent `tsc` or `turbo run typecheck` invocations fail with obscure type errors.
- **Requirement for `rc5`**: The `agyis onboard` and `agyis update` engines must automatically purge `.next/` and `.turbo/` build caches prior to executing typecheck verification gates.

### 2. Database Container Port Saturation in Multi-Repo Workstations
- **Phenomenon**: In `purrfectsoft/mm-website`, `pnpm build` failed because Next.js static prerendering of localized routes attempted to connect to Postgres on port 5432. However, a container from another local repository (`jasper_dev_postgres`) was already occupying port 5432, resulting in Prisma connection error `P1000`.
- **Requirement for `rc5`**: Multi-project environments need automated port collision detection. The `db-ops` skill and `agyis onboard` workflow must inspect port occupancy, dynamically assign isolated ports (e.g. 5433), and update `.env` `DATABASE_URL` bindings.

### 3. Husky Pre-Commit Branch Guards vs. Automated Tooling
- **Phenomenon**: `purrfectsoft/psl-website` has a Husky hook (`.husky/verify-branch-name.sh`) that strictly aborts commits directly made to `develop` without recognizing automated harness migration or rehydration workflows.
- **Requirement for `rc5`**: The onboarding engine must support isolated chore branch creation (`--create-branch chore/agyis-harness-onboarding`) as the default path, or explicitly bypass local git pre-commit hooks via `--no-verify` when direct default branch rehydration is commanded.

### 4. Single-Source Skill Deduplication Token Savings
- **Phenomenon**: Across the 5 repositories, running `agyis skills --prune-duplicates` purged between 2 and 7 redundant workspace skill copies that shadowed global plugin skills.
- **Impact**: In `knot-mesh`, 7 skills were pruned; in `purrfectcore-001`, 4 skills were pruned; in `sunshine-physio`, 5 skills were pruned. This eliminated **~4,500 redundant tokens per turn** in prompt injection contexts and eliminated all `Duplicate Skills: [WARN]` doctor diagnostics.
- **Requirement for `rc5`**: `agyis onboard` must execute `enforce_single_source_skills()` by default.

### 5. Non-Python Manifest Command Extraction Fallback (GAP-07)
- **Phenomenon**: In `kuasha420/knot-mesh`, which uses Arch Linux packaging (`PKGBUILD`) and standalone shell test suites without `pyproject.toml`, automated command extraction defaulted to generic templates until manually updated.
- **Requirement for `rc5`**: Implement Specification 3 from the gap analysis to inspect `setup.py`, `setup.cfg`, `requirements.txt`, and standalone `tests/*.sh` scripts when `pyproject.toml` is absent.

### 6. ESLint Strictness as a Next.js Production Build Blocker
- **Phenomenon**: Next.js automatically executes `next lint` during `pnpm build`. In `psl-website` PR #61, clean TypeScript compilation was blocked by strict ESLint rules (`@typescript-eslint/no-explicit-any` and dangling timers in API routes).
- **Requirement for `rc5`**: Rebase workflows on Next.js repositories must anticipate lint failures and incorporate automated lint autofix (`pnpm lint --fix`) into the verification loop.

### 7. Monorepo Vitest Test Suite Latency
- **Phenomenon**: Full-suite verification in large monorepos (e.g. `sunshine-physio` with 201 test files and 2,800+ tests) requires ~190–225s per cycle. Running this repeatedly during sequential PR rebasing creates significant latency.
- **Requirement for `rc5`**: Introduce targeted test discovery (DRA runner) during PR rebasing, running only the test files affected by the rebased commits while executing the full suite on final barrier join.

### 8. Subagent Restart Resilience & Git Idempotency
- **Phenomenon**: An unexpected workstation restart occurred midway through rebase execution.
- **Result**: Because all workers strictly adhered to atomic git operations and clean branch boundaries, every subagent seamlessly resumed execution post-restart with zero data loss, zero detached HEAD deadlocks, and zero duplicate commits.
- **Requirement for `rc5`**: Formalize the pre-flight safety patch (`.agents/artifacts/pre-rc4-safety.patch`) and safety backup branch as an invariant in all onboarding and upgrade operations.

---

## 4. Actionable Functional Specifications for Agyis v1.0.0-rc5

Based on the empirical evidence gathered from the 5-repository deployment, the following 4 core capabilities must be implemented in `v1.0.0-rc5`:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        CORE FUNCTIONAL SPECIFICATIONS FOR v1.0.0-rc5                   │
├──────────────────────────┬─────────────────────────────────────────────────────────────┤
│ 1. Unified 'onboard'     │ Single CLI command combining git topology inspection,       │
│    CLI Engine            │ decoupled presets, automated .agents/archive/ backup,       │
│    (P0)                  │ single-source skill deduplication, and rule injection.      │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 2. Automated PR Rebase & │ 'agyis rebase --pr <num>' automating fetch, rebase, cache   │
│    Cache Clearing        │ purge (.next/.turbo), native test verification, and         │
│    (P1)                  │ force-push with lease.                                      │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 3. Background Sync       │ Native 'agyis sync --service [install|status|start|stop]'   │
│    Service Management    │ command managing systemd user service and journal logging   │
│    (Issue #57, P1)       │ (eliminating manual shell workarounds).                     │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 4. Dynamic Port & Cache  │ Port collision detection in 'db-ops' and automated Next.js  │
│    Hygiene Diagnostics   │ type cache clearing in 'modern-web-guidance'.               │
│    (P1)                  │                                                             │
└──────────────────────────┴─────────────────────────────────────────────────────────────┘
```

---
*Report synthesized and recorded in repository documentation. Ready for Phase 1 Category B implementation.*
