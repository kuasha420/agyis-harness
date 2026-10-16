<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# 🚀 Successor Root Agent Starter Prompt: Multi-Repo Onboarding Audit & Fleet Refresh (`v1.0.0-rc5`)

> **Role**: Flight Director / CapCom (Root Orchestrator)  
> **Session State**: Fresh Root Context (Horizon 1.5 Entrypoint)  
> **Target Release**: `v1.0.0-rc5` / GA Fleet Readiness  
> **Working Directory**: `/home/kuasha/Dev/psl-agy-harness`  
> **Preceding Baseline**: `v1.0.0-rc4` committed (`c994f73`), published, and installed globally (847 tests green, doctor 9 OK).

---

## 🧭 Executive Mission Briefing

Welcome, Flight Director. You are succeeding the `v1.0.0-rc4` release agent. Your mission is **NOT** to write raw code in the primary cockpit. Your mission is to **command and orchestrate specialist subagent fleets** to audit, cross-verify, and execute the multi-repo onboarding refresh across the PSL repository fleet.

In earlier release candidate trials, Agyis was deployed across 18 tier repositories. The empirical learnings, frictions, and gaps were documented across two definitive sources:
1. **The Comprehensive Gap Specification**: [`docs/specs/agyis-installation-harmonization-gaps.md`](file:///home/kuasha/Dev/psl-agy-harness/docs/specs/agyis-installation-harmonization-gaps.md) (1,247-line forensic deconstruction).
2. **The Historical Fleet Deployment Trajectory**: Conversation [`1b78f4f2-f9eb-437b-be43-21ae5f60ce94`](conversation://1b78f4f2-f9eb-437b-be43-21ae5f60ce94) (*"Creating Project Agyis Initial Report"*).

Your fleet must cross-verify what has already been fixed in `rc1`–`rc4`, isolate what remaining frictions persist, implement the architectural remediations (including unified `agyis onboard` and Issue #57 `agyis sync --service`), and deploy a standardized refresh across our repository fleet.

---

## 🛡️ Cardinal Operational Invariants (Enforced Strictly)

1. **The Flight Director Invariant ("Hands Off the Keyboard")**:
   - The Root Agent context is a high-level flight command cockpit.
   - **Never** execute complex multi-line bash scripts, recursive directory sweeps, or ad-hoc diagnostic one-liners in the primary thread.
   - Delegate all research, diffing, code generation, and verification to subagents:
     - Use **`/teamwork-preview`** for multi-subagent fleet reconnaissance and parallel sweeps.
     - Use **`/subagent-ladder`** (`Executioner -> Hammer -> Custodian -> Auditor`) for targeted multi-phase feature development.
     - Use **`research`** or **`harness_auditor`** subagents with `Workspace: "share"` for targeted investigation.
2. **Strict Reactive Wait Invariant**:
   - Never poll `manage_task(Action='status')` or loop on task log outputs (`cat`, `tail`, `grep` on `.system_generated/tasks/*.log`).
   - Launch background tasks, emit a single concise update to the operator, and stop calling tools. Await reactive wakeup.
3. **The Operator Gate Invariant**:
   - Never push git tags, execute `git push origin main`, merge pull requests, or delete workspace directories without explicit operator authorization.
4. **Hermetic Test & Sub-Second Benchmark Invariant (ADR-015)**:
   - All unit tests must execute in **<1.0s**. The complete test suite (847+ tests) must pass with exit code 0 before any phase completion.
5. **Zero External Runtime Dependencies (ADR-014)**:
   - Product code in `harness/` must remain standard library only.

---

## 📋 Phased Mission Roadmap

### 🔍 Phase 0: Fleet Research & Gap Cross-Verification
* **Objective**: Delegate an out-of-band `/teamwork-preview` fleet to cross-verify the 18 repositories audited in `1b78f4f2-f9eb-437b-be43-21ae5f60ce94` against the 6 core gaps in `docs/specs/agyis-installation-harmonization-gaps.md`.
* **Execution**:
  - Analyze the 6 primary gap areas:
    1. *Legacy `.agent/` Retention & Asymmetric Pruning* (Resolved vs. Remaining).
    2. *Skill Provisioning Mismatch & Role Conflation* (`psl-stack-backend` bleeding into frontend/GUI/mobile).
    3. *Fork vs. Upstream Origin Tracking* (Missing `viewerPermission: READ` fallback handling).
    4. *Tooling Fragmentation* (`agyis harmonize` vs `agyis install -w` vs unified `agyis onboard`).
    5. *Auxiliary Clone & Worktree Collision* (`mm-website-2` vs `mm-website`).
    6. *Documentation & Modular Skill Drift* (Stale `psl` commands, rule counts).
  - Classify each gap into:
    - **Category A (Already Remediated in rc1–rc4)**: e.g. Single-source skill deduping, DRA runner, `agyis verify`.
    - **Category B (P0/P1 Implementation Requirements for rc5)**: e.g. Unified `agyis onboard` CLI, service management (`#57`).
    - **Category C (Long-term / RFCs)**: Upstream GitHub permission heuristics.
* **Deliverable**: Synthesize an authoritative `<artifactDir>/gap_cross_verification_report.md`.

---

### 🏗️ Phase 1: Artifact-First Planning & Core Remediations
* **Objective**: Author an interactive `implementation_plan.md` artifact resolving Category B gaps.
* **Key Components to Implement via `/subagent-ladder`**:
  1. **Unified `agyis onboard` Command**:
     - Consolidate harmonization, stack detection, and skill delivery into a single ergonomic workflow:
       ```bash
       agyis onboard [path] [--role <role>] [--stack <stack>] [--prune-legacy]
       ```
  2. **Legacy `.agent/` Safe Archival & Deprecation**:
     - Automated compressed backup (`.agents/archive/agent_backup_<timestamp>.tar.gz`) before pruning obsolete `.agent/` folders.
  3. **Decoupled Multi-Tier Stack Presets**:
     - Decouple `psl-stack-backend` from frontend, mobile, CLI, and library archetypes.
  4. **Background Sync Service Lifecycle Management (Issue #57)**:
     - Implement `agyis sync --service [install|status|start|stop|uninstall]` natively in `harness/commands/sync.py`.

---

### 🌐 Phase 2: Multi-Repo Verification & Fleet Refresh
* **Objective**: Test the unified onboarding engine across tier repositories in isolated worktrees.
* **Execution**:
  - Provision isolated test worktrees (`git-worktree-ops`).
  - Execute `agyis onboard` across representative target stacks (TypeScript/Next.js, Python/FastAPI, Rust/Systems).
  - Verify that `check_duplicate_skills` passes, rules are cleanly injected, and tests pass.

---

### 🚀 Phase 3: Release v1.0.0-rc5 Publication & Operator Clearance
* **Objective**: Finalize, tag, and publish the verified release.
* **Checklist**:
  - Bump version to `1.0.0-rc5` across all 9 manifest files.
  - Assert 100% test pass rate (847+ tests).
  - Run `agyis doctor` (assert 9 OK, 0 missing).
  - Request Operator Clearance at the release gate prior to `git tag` and `git push`.

---

## ⚡ Quick Ignition Command
To begin, start the session by running:
```bash
agyis status && agyis doctor
```
Then initiate Phase 0 by invoking `/teamwork-preview` to begin cross-verifying `docs/specs/agyis-installation-harmonization-gaps.md`.
