<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Architectural Specification: Agyis Installation, Harmonization & Fleet Onboarding Gaps

```
Document Status : Approved Specification / Ready for Implementation
Document Version: 1.0.0
Date            : 2026-10-13
Authors         : Agyis Lead Architecture Working Group (@kuasha420)
Target Scope    : harness/ (commands, delivery, skills), docs/ (specs, runbooks), .agents/skills/
Target Engine   : Agyis Harness (v1.0.0-rc1 -> v1.0.0-rc2)
Classification  : Corporate Standard Architecture Specification & Draft ADR-031
```

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Empirical Transcript Forensics (R1)](#2-empirical-transcript-forensics-r1)
   - [2.1 Legacy `.agent/` Directory Retention & Asymmetric Pruning](#21-legacy-agent-directory-retention--asymmetric-pruning)
   - [2.2 Skill Provisioning Mismatch & Architectural Role Conflation](#22-skill-provisioning-mismatch--architectural-role-conflation)
   - [2.3 Fork vs. Upstream Origin Tracking & Cross-Repo PR Detection](#23-fork-vs-upstream-origin-tracking--cross-repo-pr-detection)
   - [2.4 Global vs. Local Workspace Agent Boundaries & Deduplication](#24-global-vs-local-workspace-agent-boundaries--deduplication)
   - [2.5 Auxiliary Worktree & Multi-Clone Handling (`mm-website-2`)](#25-auxiliary-worktree--multi-clone-handling-mm-website-2)
   - [2.6 Self-Referential Harness Host Verification Checks](#26-self-referential-harness-host-verification-checks)
   - [2.7 Uncommitted Work Safeguarding, Syntax Bugs & Swarm Interventions](#27-uncommitted-work-safeguarding-syntax-bugs--swarm-interventions)
3. [Product & CLI Architecture Gap Analysis (R2)](#3-product--cli-architecture-gap-analysis-r2)
   - [3.1 Harmonization Delivery Engine (`harness/delivery/harmonize.py`)](#31-harmonization-delivery-engine-harnessdeliveryharmonizepy)
   - [3.2 Harmonization CLI Parser & Command Module (`harness/cli.py`, `harness/commands/harmonize.py`)](#32-harmonization-cli-parser--command-module)
   - [3.3 Stack Detection Waterfall Heuristics (`harness/skills/__init__.py`)](#33-stack-detection-waterfall-heuristics-harnessskills__init__py)
   - [3.4 Stack Skill Presets Hardcoding (`harness/skills/__init__.py`)](#34-stack-skill-presets-hardcoding-harnessskills__init__py)
   - [3.5 Workspace Command Extraction & Legacy Notice (`harness/delivery/workspace.py`)](#35-workspace-command-extraction--legacy-notice-harnessdeliveryworkspacepy)
   - [3.6 Git Hygiene Exclusion Contamination & Git Blindness (`harness/delivery/constants.py`, `git_hygiene.py`)](#36-git-hygiene-exclusion-contamination--git-blindness)
   - [3.7 Command Overlap Ambiguity: `agyis init` vs. `agyis install -w`](#37-command-overlap-ambiguity-agyis-init-vs-agyis-install--w)
4. [Documentation & Developer Experience Gap Analysis (R3)](#4-documentation--developer-experience-gap-analysis-r3)
   - [4.1 Residual `psl` vs. `agyis` Nomenclature Drift](#41-residual-psl-vs-agyis-nomenclature-drift)
   - [4.2 Modular Skills Documentation Drift & Broken Guidance](#42-modular-skills-documentation-drift--broken-guidance)
   - [4.3 Specifications for 4 Missing Operational Runbooks](#43-specifications-for-4-missing-operational-runbooks)
   - [4.4 CLI Help Text Normalization & Argument Consistency](#44-cli-help-text-normalization--argument-consistency)
5. [Comprehensive Remediation Specification (R4)](#5-comprehensive-remediation-specification-r4)
   - [5.1 Comprehensive Gap Taxonomy Matrix](#51-comprehensive-gap-taxonomy-matrix)
   - [5.2 CLI Command Specifications: `harmonize` Evolution & Unified `onboard`](#52-cli-command-specifications-harmonize-evolution--unified-onboard)
   - [5.3 Legacy Directory Deprecation & Pruning Lifecycle Algorithm](#53-legacy-directory-deprecation--pruning-lifecycle-algorithm)
   - [5.4 Decoupled Multi-Tier Stack Preset Architecture](#54-decoupled-multi-tier-stack-preset-architecture)
   - [5.5 Fork-Aware Remote Detection & PR Submission Pipeline](#55-fork-aware-remote-detection--pr-submission-pipeline)
   - [5.6 Documentation & Modular Skills Remediation Plan](#56-documentation--modular-skills-remediation-plan)
6. [Draft Architecture Decision Record (ADR-031)](#6-draft-architecture-decision-record-adr-031)
7. [Verification & Acceptance Criteria](#7-verification--acceptance-criteria)

---

## 1. Executive Summary

### 1.1 Retrospective Context
On October 13, 2026, an autonomous multi-agent engineering swarm executed a fleet-wide onboarding campaign across 18 software repositories spanning three GitHub organizations and namespaces: `purrfectsoft`, `kuasha420`, and `sakibtamim`. The mission objective was to transition all active codebases to the newly published **Agyis Harness (`v1.0.0-rc1`)**, inject canonical `AGYIS-HARNESS` tagged invariant rules blocks, provision stack-tailored modular skills, safeguard all in-flight uncommitted local work, execute hermetic verification, and open official pull requests against each repository's active branch.

### 1.2 Core Audit Findings
The campaign achieved **100% preservation of invariant rules and zero data or work loss**:
- All 18 repositories were successfully analyzed.
- Zero uncommitted local modifications were lost (high-value feature WIP in `purrfectcore-001` was preserved via git patch and safety branch; experimental items in `Jasper` were isolated via git stash and safety branch).
- 17 production Pull Requests were cleanly opened on GitHub (with `psl-agy-harness` recognized as the self-referential harness host).
- Canonical rule fences (`<!-- Added by AGYIS-HARNESS --> ... <!-- End AGYIS-HARNESS -->`) were injected with zero corruption of pre-existing user markdown instructions.

However, an exhaustive empirical forensics review of 12 conversation transcripts and task logs across the parent agent, sentinels, sub-orchestrators, workers, challengers, reviewers, and auditors revealed that the fleet onboarding campaign required **extensive manual interventions, ad-hoc python scripts, and custom shell workarounds**. 

These frictions stemmed directly from **6 fundamental architectural and documentation gaps** in the Agyis product:
1. **Passive Harmonization & Missing Legacy Lifecycle**: `agyis harmonize` performed a non-destructive copy of files from `.agent/` to `.agents/` without providing any automated mechanism to prune, archive, or stage the removal of the obsolete `.agent/` directory, causing test suite failures and worker divergence.
2. **Coupled Stack Presets & Architectural Conflation**: Default stack presets hardcoded `psl-stack-backend` into all TypeScript, Python, Node, and Go workspaces, forcing backend database transaction and tenant-isolation skills onto pure client, GUI, and mobile applications.
3. **Fork & Permission Blindness**: The CLI and verification engines assumed direct write access to `origin`, failing to detect personal forks, missing GitHub push permissions (`viewerPermission: READ`), and cross-repository PR workflows.
4. **Tooling Fragmentation & Ergonomic Disconnect**: `agyis harmonize` migrated rules but did not provision skills; `agyis install` defaulted to global plugin installation; workers lacked a unified `agyis onboard` workflow, forcing manual fallback to `mkdir -p .agents/skills && cp -r`.
5. **Auxiliary Clone & Worktree Collision**: Fleet inventory tools lacked heuristics to differentiate canonical checkouts from auxiliary worktrees (e.g. `mm-website-2` vs `mm-website`).
6. **Documentation & Modular Skill Drift**: Critical modular skills (`psl-harmonize`, `agent-builder`, `subagent-ladder`) contained stale commands (`python3 -m harness.cli`, `psl`), obsolete paths (`~/.gemini/antigravity/agents/`), legacy rule markers (`<!-- Added by PSL-HARNESS -->`), and obsolete rules counts ("5 Ground Rules" vs. 8 canonical empirical rules).

This specification provides the definitive, publication-grade architectural blueprint to resolve all 6 gaps, establishing a unified onboarding lifecycle, decoupled multi-tier stack presets, fork-aware remote automation, and complete documentation alignment.

---

## 2. Empirical Transcript Forensics (R1)

This forensic analysis examines 12 conversation transcripts, 18 target repositories, and associated subagent logs from the 2026-10-13 fleet onboarding session.

```
Primary Transcripts Audited:
• Parent Agent Orchestrator: /home/kuasha/.gemini/antigravity/brain/f2855e28-fe0d-4f60-8160-2fbe3fdf2b16/.system_generated/logs/transcript.jsonl (354 steps)
• Teamwork Sentinel         : /home/kuasha/.gemini/antigravity/brain/5d1e1849-a72e-467e-8a37-378fbe242236/.system_generated/logs/transcript.jsonl (315 steps)
• Sub-Orchestrator M3       : /home/kuasha/.gemini/antigravity/brain/7c2332c9-89e7-47a2-92ed-924fd7efaf22/.system_generated/logs/transcript.jsonl (253 steps)
• Subagent Worker Transcripts:
  - m1_worker_triage    (37ecaa9c-e2d6-480c-aa59-f3ee065c54c7)
  - m2_worker_kuasha    (c807cc7a-e159-4832-97a2-4809a44bc419)
  - m3_worker_sakibtamim(c15aa052-bc5a-4f09-b8b5-db788fa10318)
  - m4_worker_purrfect  (5d5a0142-48b8-433f-91de-a97d7f337330, 276 steps)
  - m5_worker_infra     (8b1f16ba-0a93-474b-b5c5-8a52c480b3a9)
  - m6_challenger       (1014eec0-835f-4a60-81c1-4d62fb71750f)
  - m6_reviewer         (6fe3af27-93d2-4b84-931d-7eeca11d9d47)
  - m6_auditor          (f7944741-b85a-47ae-ad34-a78f42f6f2e6, 184 steps)
  - sub_orch_e2e / verify_fleet.py (.agents/teamwork/sub_orch_e2e/verify_fleet.py)
```

---

### 2.1 Legacy `.agent/` Directory Retention & Asymmetric Pruning

#### A. Code Mechanism & Passive Migration
In `harness/delivery/harmonize.py` lines 143–215, `harmonize_workspace()` scans `legacy_agent_dir = ws / ".agent"` and executes copy operations:
- Lines 144–162: Copies `.agent/agents/*.md` to `.agents/agents/`
- Lines 164–194: Synthesizes `.agent/workflows/*.md` into `.agents/skills/<name>/SKILL.md`
- Lines 196–215: Recursively copies `.agent/rules/*` to `.agents/rules/`

The engine contains **zero deletion, moving, unlinking, or git staging logic**. `harness/commands/harmonize.py` accepts only `path`, `--dry-run`, and `--json`. Neither `--prune-legacy` nor `--clean-agent-dir` exists.

#### B. Verification Contract Failure
In `/home/kuasha/Dev/psl-agy-harness/.agents/teamwork/sub_orch_e2e/verify_fleet.py` lines 595–614, Tier 1 verification asserted an uncompromising negative check:
```python
legacy_dir = repo_dir / ".agent"
if not legacy_dir.exists():
    results.append(AssertionResult(tier=1, name="no_legacy_agent_dir", status=TestStatus.PASS, ...))
else:
    results.append(AssertionResult(tier=1, name="no_legacy_agent_dir", status=TestStatus.FAIL, ...))
```
Because `agyis harmonize` left `.agent/` intact on disk, standard harmonized repositories immediately failed Tier 1 verification.

#### C. Divergent Subagent Strategies
1. **Worker `m3_worker_sakibtamim`**:
   In transcript `c15aa052-bc5a-4f09-b8b5-db788fa10318`, Steps 205–207 (2026-10-13T13:25:33Z):
   Worker noticed `.agent` persisted after running `agyis harmonize /home/kuasha/Dev/purrfect-download-manager`. Recognizing that the presence of `.agent` would violate fleet cleanliness, the worker manually executed:
   ```bash
   git -C /home/kuasha/Dev/purrfect-download-manager rm -r .agent
   ```
   The worker repeated this manual `git rm -r .agent` in `Jasper` (Step 35 in `m3_worker_sakibtamim/onboarding_report.md`).
2. **Workers `m4_worker_purrfect` and `m5_worker_infra`**:
   Interpreting ADR-014 literally ("non-destructive migration"), workers preserved `.agent/` intact on disk and tracked in git across 8 repositories: `purrfectcore-001`, `purrfectcore-client`, `psl-boilerplate`, `psl-scaffold`, `psl-website`, `mm-website`, `purrmission`, and `chronicle-time-keeper`.
   As documented by `m6_reviewer` in `review_report.md` (lines 106–108):
   > *"Observation: In `purrfectcore-001`, `purrfectcore-client`, `psl-boilerplate`, `psl-scaffold`, `psl-website`, `mm-website`, `purrmission`, and `chronicle-time-keeper`, the legacy `.agent/` directory remains tracked alongside `.agents/`... `agyis harmonize` is designed non-destructively to copy rule files without deleting `.agent/`. In contrast, in `Jasper` and `purrfect-download-manager`, worker `m3` explicitly ran `git rm -r .agent`."*

#### D. The Emergency `heal_fleet.py` Intervention
When the parent agent ran `verify_fleet.py` at Step 253 (2026-10-13T14:11:51Z in `f2855e28...`), Tier 1 failed across all 8 repositories.
At Step 271 (2026-10-13T14:13:21Z), the parent agent authored an emergency ad-hoc script at `/home/kuasha/.gemini/antigravity/brain/f2855e28-fe0d-4f60-8160-2fbe3fdf2b16/scratch/heal_fleet.py`:
```python
# Lines 36-42 of scratch/heal_fleet.py:
legacy_agent = repo_path / ".agent"
modern_agents = repo_path / ".agents"
if legacy_agent.exists() and modern_agents.exists():
    subprocess.run(["git", "-C", str(repo_path), "rm", "-rf", ".agent"], stderr=subprocess.DEVNULL)
    if legacy_agent.exists():
        shutil.rmtree(legacy_agent)
```
Executed as background `task-274`, `heal_fleet.py` executed `git rm -rf .agent`, committed `chore: clean legacy .agent and provision psl-stack-backend skill`, and pushed updates to remote origin across all 8 repositories (`task-274.log`).

---

### 2.2 Skill Provisioning Mismatch & Architectural Role Conflation

#### A. Code Root Cause in Harness Presets
In `harness/skills/__init__.py` lines 80–104, preset definitions tightly bundle backend architectural roles into language stacks:
```python
    "python": [
        "psl-stack-python",
        "psl-test-python",
        "psl-stack-backend",
    ],
    "typescript": [
        "psl-stack-typescript",
        "psl-test-node",
        "psl-stack-backend",
    ],
    "node": [
        "psl-stack-typescript",
        "psl-test-node",
        "psl-stack-backend",
    ],
```
When `detect_workspace_stack()` finds `package.json`, it returns `"typescript"`. Consequently, any project with `package.json` receives `psl-stack-backend`.

#### B. Verification Suite Demand vs. Domain Reality
In `verify_fleet.py` lines 245–398, `DEFAULT_FLEET_SPECS` copied `STACK_SKILL_PRESETS["typescript"]` verbatim, asserting that `psl-stack-backend` must exist in:
- Desktop PyQt GUI app: `jimha`
- React Native Mobile apps: `react-native-template-ts-plus`, `sunshine-physio-universalapp`
- Desktop Electron/Next.js app: `purrfect-download-manager`
- Frontend Web/UI libraries: `mm-website`, `psl-website`, `psl-boilerplate`, `purrfectcore-client`
- Developer CLI tool: `psl-scaffold`
- Discord bot: `purrmission`

#### C. Subagent Domain Pruning & Challenger Report
Workers `m2_worker_kuasha` and `m4_worker_purrfect` observed that pure client and GUI codebases have no SQL databases, connection pools, or multi-tenant transaction logic. Installing `psl-stack-backend` into a client app injects irrelevant invariants (e.g. `tenant_id` database scoping, repository patterns). Workers intentionally installed only `psl-stack-typescript` and `psl-test-node`.

In `m6_challenger/challenge_report.md` (lines 27–38), `m6_challenger` flagged this:
> *"Challenge 1: Test Suite Over-Specification of `psl-stack-backend` in `verify_fleet.py`... flagged 11 repositories as failing Tier 3... If workers had blindly installed `psl-stack-backend` into pure client or GUI repositories, they would violate the PSL principle of stack-tailored modular skills and pollute frontends with backend database transaction and tenant-isolation skills."*

#### D. Forceful Pollution via `heal_fleet.py`
To satisfy the rigid test suite, parent agent's `heal_fleet.py` (lines 45–49) copied `/home/kuasha/Dev/psl-agy-harness/.agents/skills/psl-stack-backend` into all 12 client repositories, committed them, and pushed them to remote origin (commits `cda6568` in `sunshine-physio-universalapp`, `b08ac64` in `react-native-template-ts-plus`, `1f19661` in `jimha`), polluting client repositories with backend server specifications.

---

### 2.3 Fork vs. Upstream Origin Tracking & Cross-Repo PR Detection

#### A. Upstream 403 Permission Failure in `sakibtamim/purrfect-download-manager`
In transcript `c15aa052-bc5a-4f09-b8b5-db788fa10318` Step 225 (2026-10-13T13:26:33Z):
```bash
git -C /home/kuasha/Dev/purrfect-download-manager push -u origin chore/agyis-harness-onboarding
```
Failed with:
```text
remote: Permission to sakibtamim/purrfect-download-manager.git denied to kuasha420.
fatal: unable to access 'https://github.com/sakibtamim/purrfect-download-manager.git/': The requested URL returned error: 403
```
- **Worker Triage**: At Step 229 (13:26:44Z), worker probed permissions: `gh repo view sakibtamim/purrfect-download-manager --json viewerPermission` -> `"READ"`.
- At Step 243 (13:27:30Z), worker configured a fork remote: `gh repo fork --remote=true --remote-name=fork`.
- At Step 247 (13:27:43Z), pushed to `fork`: `git push -u fork chore/agyis-harness-onboarding`.
- At Step 249 (13:27:51Z), opened cross-repo PR: `gh pr create --repo sakibtamim/purrfect-download-manager --base develop --head kuasha420:chore/agyis-harness-onboarding` -> PR #23.
- **Verification Engine Incompatibility**: In `verify_fleet.py` line 923, verification hardcoded `git ls-remote --heads origin target_branch`. Because the branch was pushed to `fork` and not `origin`, verification failed Tier 4: `Branch 'chore/agyis-harness-onboarding' has not been pushed to remote origin`.
- **Healing Script Regression**: At Step 274 (14:13:47Z in parent), `heal_fleet.py` line 60 ran `git push origin branch`, triggering the 403 error again (line 203 in `task-274.log`).
- **Parent Patch**: At Step 319 (14:17:07Z), parent agent edited `verify_fleet.py` lines 928–936 to probe `fork` remote when `origin` fails.

#### B. Dual PR Topology in `purrmission`: Canonical `kuasha420` vs. Fork `purrfectsoft`
- In parent transcript Step 200 (13:24:54Z), the operator intervened:
  `<USER_REQUEST> Hey purmission is canonically on kuasha420 - the purrfectsoft is experimental fork. Both should be updated. </USER_REQUEST>`
- In `m4_worker_purrfect` transcript `5d5a...` Steps 159–165:
  Worker pushed to `origin` and opened PR #161 on `kuasha420/purrmission` (`--base master`), then pushed to remote `purrfectsoft` and opened PR #4 on `purrfectsoft/purrmission` (`--base master`).
- Auxiliary directory `/home/kuasha/Dev/purrmission/purrmission-worktrees/` existed on disk, requiring explicit exclusions to avoid git command corruption.

---

### 2.4 Global vs. Local Workspace Agent Boundaries & Deduplication

#### A. Authoritative Requirement
`ORIGINAL_REQUEST.md` R2 (line 163) explicitly commanded:
> *"Retain agent definitions globally in Antigravity to avoid unnecessary repository bloat, while preserving any existing project-specific agent overrides."*

#### B. Code Disconnect
In `harness/delivery/harmonize.py` lines 143–162:
```python
src_agents_dir = legacy_agent_dir / "agents"
if src_agents_dir.is_dir():
    for item in sorted(src_agents_dir.glob("*.md")):
        shutil.copy2(item, dst_file)
```
`harmonize` unconditionally copies all `.agent/agents/*.md` to `<workspace>/.agents/agents/`. It does not cross-reference `~/.gemini/config/plugins/agyis-harness/agents/` or `~/.gemini/config/agents/` to prevent duplicating global personas into local repositories.

#### C. Empirical Behavior
Workers in the onboarding session disciplined themselves not to run `agyis init --agents` or `agyis agents --sync`.
Forensic inspection of all 18 repositories revealed `.agents/agents/` present in only two repositories:
1. `psl-agy-harness` (harness product repo itself).
2. `knot-mesh` (`swarm_orchestrator.md`, an intentional project-specific governance specialist override).
Zero standard personas were leaked into client repositories, preserving cleanliness through manual discipline rather than automated CLI safeguards.

---

### 2.5 Auxiliary Worktree & Multi-Clone Handling (`mm-website-2`)

#### A. Physical Layout
In `/home/kuasha/Dev`:
- `/home/kuasha/Dev/mm-website`: Primary repository checkout pointing to `https://github.com/purrfectsoft/mm-website.git` on base branch `develop`.
- `/home/kuasha/Dev/mm-website-2`: Auxiliary clone of `https://github.com/purrfectsoft/mm-website.git` on branch `copilot/add-mcp-support-for-copilot`.

#### B. Survey & Verification Friction
In `verify_fleet.py` lines 358–365, `mm-website-2` was registered as an independent target repository in `DEFAULT_FLEET_SPECS`.
When `verify_fleet.py` executed, it demanded that `mm-website-2` have its own `chore/agyis-harness-onboarding` branch and distinct PR.
However, `mm-website` had already onboarded the repository and opened PR #411 on GitHub against `develop`. Attempting to open a duplicate PR for `mm-website-2` against the same repository failed.

#### C. Manual Filtering Patch
In parent transcript Step 293 (14:15:04Z), the parent investigated `is_auxiliary_clone`. At Step 314 (14:16:50Z), the parent patched `verify_fleet.py` line 1078:
```python
specs = [s for s in specs if not s.is_auxiliary_clone and not s.is_harness_host]
```

---

### 2.6 Self-Referential Harness Host Verification Checks

#### A. Host Registration
In `verify_fleet.py` lines 264–271, `psl-agy-harness` was registered as a client onboarding target in `DEFAULT_FLEET_SPECS`:
```python
TargetRepoSpec(
    name="psl-agy-harness",
    relative_path="psl-agy-harness",
    account="kuasha420",
    stack="python",
    expected_skills=["psl-stack-python", "psl-test-python"],
    base_branch="main",
    is_harness_host=True,
)
```

#### B. Verification Failures
- **Tier 1 (Harmonization)**: `verify_fleet.py` checked for root `AGENTS.md` containing `<!-- Added by AGYIS-HARNESS -->`. But `psl-agy-harness` is the harness engine itself; its root rule definition is located in `.agents/rules/AGENTS.md` and does not contain self-injected tags.
- **Tier 4 (PR Lifecycle)**: `verify_fleet.py` demanded a pushed `chore/agyis-harness-onboarding` branch and an open GitHub PR. But `psl-agy-harness` was already committed cleanly on `main` at `v1.0.0-rc1`. Creating a client onboarding PR against itself was nonsensical.
- **Resolution**: Patched at Step 314 (`if not s.is_harness_host`).

---

### 2.7 Uncommitted Work Safeguarding, Syntax Bugs & Swarm Interventions

#### A. Uncommitted Work Triage
1. **`purrfectcore-001`**:
   - Initial state: 14 modified uncommitted files (+120/-62 lines) in advocate-referral features/specs; local `develop` was 71 commits behind `origin/develop` (`ad7a97c2` vs `fb0b172c`).
   - Triage by `m1_worker_triage` (`37ecaa9c...`):
     Exported patch `.agents/teamwork/m1_worker_triage/purrfectcore-001-advocate-referral.patch` (20,321 bytes, 461 lines).
     Created safety branch `backup/uncommitted-advocate-referral` at commit `86c73f5c`.
     Cleanly fast-forwarded `develop` to `origin/develop` before branching `chore/agyis-harness-onboarding`.
2. **`Jasper`**:
   - Initial state: Untracked `.agents/skills/psl-stack-backend/`, `psl-stack-typescript/`, and root `AGENTS.md`.
   - Invariant: `.agents/AGENTS.md` contained the 10-minute PR review delay fence and pre-merge check script (605 bytes, SHA256 `c6813e0c...`), but was untracked due to root `.gitignore:48:.agents/*`.
   - Triage by `m1_worker_triage`:
     Exported patch `jasper-untracked-agent-items.patch` (14,540 bytes).
     Created safety branch `backup/untracked-agent-items` at commit `f6873a0`.
     Created git stash `stash@{0}` on `master`.
     Patched `.gitignore` whitelisting to guarantee tracking.

#### B. Python Compatibility Syntax Bug in `jimha`
In `m2_worker_kuasha` transcript `c807...` Step 115 (13:11:50Z):
`tests/test_jimha.py` line 998 contained an f-string expression with an escaped backslash (`f"{'\\\"'}"`), which raises a `SyntaxError` in Python runtimes <= 3.11.
Worker `m2` manually patched `tests/test_jimha.py` line 998 to decouple the expression into `expected_escape = json.dumps('window"with"quotes')` before `python3 -m unittest` could pass.

#### C. Antigravity Stop Hook Blocked Termination
In parent transcript Step 324 (14:17:46Z):
When parent agent modified `verify_fleet.py` to fix fork checking and auxiliary clone exclusions, Antigravity's harness stop hook intercepted and blocked the agent's turn:
```text
<SYSTEM_MESSAGE>
Stop hook blocked termination: Verification Required: Unverified code edits detected in:
/home/kuasha/Dev/psl-agy-harness/.agents/teamwork/sub_orch_e2e/verify_fleet.py.
Execute 'agyis test' (or 'python3 -m harness.cli test') or your project test command.
</SYSTEM_MESSAGE>
```
The agent was forced to execute `python3 -m harness.cli test` (576/576 tests OK in 4.39s) before it was permitted to conclude the turn.

#### D. Disconnected Tooling & Fallback to `cp -r`
Across workers `m2`, `m3`, and `m4`, agents did NOT use `agyis install` or `agyis init` to provision skills.
Because `agyis harmonize` does not provision skills, and `agyis install` defaults to `--global` (installing the plugin into Antigravity user config), workers repeatedly ran:
```bash
mkdir -p <repo>/.agents/skills && cp -r /home/kuasha/Dev/psl-agy-harness/.agents/skills/<skill> <repo>/.agents/skills/
```
Only `m5_worker_infra` discovered and used `python3 -m harness.cli skills --sync --workspace <repo> --skills <list>`.

#### E. Operator Directives & Token Pauses
- **13:59:09Z**: Operator Directive: *"Pause after the handoff - we are running low on tokens"*.
- **14:07:42Z (Parent L231)**: Operator Directive: *"We are runnig dangerously close to token limuits. Please save and pause work immediately"*.
- **14:08:35Z (Parent L242)**: Operator Directive: *"You shouldn't have killed the fleet orc - just asked it to gracefully pause. WTF"*.
  Parent had invoked `manage_task(Action='kill')` on the running orchestrator rather than issuing a graceful pause message, causing operator alarm.
- **14:11:13Z (Parent L244)**: Operator Directive: *"We are back. Let's actually do the victory audit"*.

---

## 3. Product & CLI Architecture Gap Analysis (R2)

A rigorous audit of the `harness/` codebase reveals seven technical root causes responsible for the empirical friction documented above.

```
Codebase Locations Audited:
• harness/delivery/harmonize.py:143-215 (Harmonization engine)
• harness/cli.py:308-333               (CLI argument parsing)
• harness/commands/harmonize.py:20-66  (Harmonize command handler)
• harness/skills/__init__.py:80-209    (Presets & stack detection)
• harness/delivery/workspace.py:138-309(Command extraction & install)
• harness/delivery/constants.py:49-55  (Git exclude patterns)
• harness/delivery/git_hygiene.py:21-86(Git hygiene functions)
• harness/commands/install.py:104-106  (Install/Init entrypoint overlap)
```

---

### 3.1 Harmonization Delivery Engine (`harness/delivery/harmonize.py`)

#### A. Passive Copy-Only Execution
In `harness/delivery/harmonize.py`:
- Lines 130–131:
  ```python
  legacy_agent_dir = ws / ".agent"
  legacy_agent_dir_found = legacy_agent_dir.is_dir()
  ```
- Lines 144–162: Scans `legacy_agent_dir / "agents"`, performs byte comparison, and copies via `shutil.copy2(item, dst_file)` into `.agents/agents/`.
- Lines 164–194: Scans `legacy_agent_dir / "workflows"`, parses markdown frontmatter via `synthesize_skill_frontmatter`, and writes synthesized content to `.agents/skills/<name>/SKILL.md`.
- Lines 196–215: Scans `legacy_agent_dir / "rules"`, recursively copies files via `shutil.copy2(item, dst_file)` into `.agents/rules/<rel_path>`.
- Lines 217–270: Extracts command dictionary and injects or updates `AGENTS.md` tagged block `<!-- Added by AGYIS-HARNESS --> ... <!-- End AGYIS-HARNESS -->`.

**Critical Implementation Flaw**:
`harmonize.py` contains **zero unlinking, moving, renaming, or deletion logic**. Searching for `rmtree`, `unlink`, or `remove` yields zero matches. The legacy `.agent/` directory remains 100% intact on disk after execution.

#### B. Orphaned Legacy Subdirectories & Untracked File Persistence
`harmonize.py` only inspects three specific subdirectories: `agents/`, `workflows/`, and `rules/`. Any other directories or files inside `.agent/`—such as `.agent/skills/`, `.agent/context/`, `.agent/config.json`, or `.agent/scratch/`—are completely ignored, leaving orphaned debris behind. Furthermore, when pruning is attempted solely via `git rm -rf .agent`, untracked files are skipped by Git and persist on disk (`(ws / ".agent").exists()` remains `True`), failing Tier 1 repository cleanliness tests unless explicitly backed up and removed via `shutil.rmtree()` (Challenger 2 CHAL-01).

#### C. User Rule Reference Blindness
`harmonize.py` inspects `AGENTS.md` only to replace or inject the tagged block. It does not inspect existing user rules outside the tagged fence. If user markdown contains references like `See .agent/rules/coding-standards.md`, those links become broken paths when `.agents/` is introduced.

---

### 3.2 Harmonization CLI Parser & Command Module

#### A. Missing CLI Flags in `harness/cli.py`
In `harness/cli.py` lines 308–315:
```python
    # harmonize
    p_harm = subparsers.add_parser(
        "harmonize", help="Harmonize legacy .agent/ directories and PSL-HARNESS rules into modern .agents/ structure"
    )
    p_harm.add_argument("path", nargs="?", default=None, help="Target workspace path (defaults to current directory)")
    p_harm.add_argument("--dry-run", action="store_true", help="Preview harmonization actions without modifying files")
    p_harm.add_argument("--json", action="store_true", help="Output harmonization report in JSON format")
```
The CLI accepts only `path`, `--dry-run`, and `--json`. There are zero arguments to:
- Prune or stage removal of `.agent/` (`--prune-legacy`, `--clean-agent-dir`).
- Archive `.agent/` before removal (`--backup`, `--backup-dir`).
- Provision stack-tailored skills during harmonization (`--stack`, `--skills`).

#### B. Misleading Command Output in `harness/commands/harmonize.py`
In `harness/commands/harmonize.py`:
- Line 41: Prints `• Legacy .agent/ found: {'yes' if res.legacy_agent_dir_found else 'no'}`.
- Line 64: Prints `• Disk status: Harmonization applied cleanly`.
The CLI informs the user that a legacy `.agent/` directory was detected, but provides no instruction or mechanism to clean it up.

---

### 3.3 Stack Detection Waterfall Heuristics (`harness/skills/__init__.py`)

In `harness/skills/__init__.py` lines 184–209:
```python
def detect_workspace_stack(workspace_root: Optional[Path] = None) -> Optional[str]:
    root = Path(workspace_root) if workspace_root else find_workspace_root()
    if (root / "tsconfig.json").is_file() or (root / "package.json").is_file():
        return "typescript"
    if (
        (root / "pyproject.toml").is_file()
        or (root / "requirements.txt").is_file()
        or (root / "setup.py").is_file()
    ):
        return "python"
    if (root / "Cargo.toml").is_file():
        return "rust"
    if (root / "go.mod").is_file():
        return "go"
    if (
        (root / "Makefile").is_file()
        or (root / "CMakeLists.txt").is_file()
        or (root / "meson.build").is_file()
        or (root / "flake.nix").is_file()
        or (root / "PKGBUILD").is_file()
    ):
        return "systems"
    return None
```

#### Defect 1: Rigid Waterfall & `package.json` Dominance
If a repository contains a root `package.json` solely for Prettier, Husky, or documentation (e.g. in a Python or Rust project), line 189 matches immediately and returns `"typescript"`. Python, Rust, Go, or Systems markers are never evaluated.

#### Defect 2: Blind JavaScript vs. TypeScript Conflation
`package.json` without `tsconfig.json` returns `"typescript"`. Pure JavaScript projects are misidentified as TypeScript.

#### Defect 3: Shell Script Blindness
There is no heuristic for shell repositories (`*.sh`, `bin/`). Line 209 returns `None`. When `None` is returned, `harness/delivery/workspace.py:315` defaults to `"generic"`, resulting in zero skills being provisioned.

#### Defect 4: Polyglot Monorepo Blindness
`detect_workspace_stack()` evaluates manifests strictly at `root`. In polyglot monorepos where root contains only build orchestrator configurations (such as Turborepo, pnpm workspaces, Lerna, Nx with root `package.json`), backend Python microservices (`services/api/pyproject.toml`) and Go background workers (`services/worker/go.mod`) are completely ignored (Challenger 2 CHAL-04). The entire repository is misidentified as pure TypeScript, depriving backend and worker services of appropriate language and testing skills.

---

### 3.4 Stack Skill Presets Hardcoding (`harness/skills/__init__.py`)

In `harness/skills/__init__.py` lines 80–125:
```python
    "python": [
        "psl-stack-python",
        "psl-test-python",
        "psl-stack-backend",
    ],
    "typescript": [
        "psl-stack-typescript",
        "psl-test-node",
        "psl-stack-backend",
    ],
    "node": [
        "psl-stack-typescript",
        "psl-test-node",
        "psl-stack-backend",
    ],
    "javascript": [
        "psl-stack-typescript",
        "psl-test-node",
        "psl-stack-backend",
    ],
    "go": [
        "psl-test-go",
        "psl-stack-backend",
    ],
```
`psl-stack-backend` is hardcoded unconditionally into `python`, `typescript`, `node`, `javascript`, and `go` presets.
This architecture conflates **Language Runtime** with **Architectural Role**, forcing backend database transaction and tenant-isolation skills onto frontend web apps, React Native templates, Electron apps, and CLI tools.

---

### 3.5 Workspace Command Extraction & Legacy Notice (`harness/delivery/workspace.py`)

#### A. Unreachable Dead Code in Python Command Extraction
In `harness/delivery/workspace.py` lines 158–170:
```python
158:         if "test" not in commands:
159:             has_pytest = (
160:                 "pytest" in tools
161:                 or (ws / "tests").is_dir()
162:                 or (ws / "test").is_dir()
163:                 or (ws / "pytest.ini").is_file()
164:                 or (ws / "setup.cfg").is_file()
165:             )
166:             if has_pytest:
167:                 commands["test"] = f"{prefix}pytest"
168:             elif (ws / "tests").is_dir():
169:                 commands["test"] = f"{prefix}python3 -m unittest discover -s tests -v"
```
Line 161 includes `(ws / "tests").is_dir()` inside `has_pytest`. Consequently, whenever `tests/` exists, `has_pytest` evaluates to `True`.
The `elif (ws / "tests").is_dir():` on line 168 is **unreachable dead code**. Projects using standard `unittest` without `pytest` (e.g. `jimha`) are erroneously assigned `pytest`.

#### B. Command Extraction Bypassed When `pyproject.toml` is Missing
In `harness/delivery/workspace.py`:
- Line 138: `if pyproj.is_file():` wraps all Python command detection.
If a Python project uses `setup.py`, `setup.cfg`, or `requirements.txt` without `pyproject.toml`, the entire block is skipped, extracting zero test or lint commands.

#### C. Outdated Legacy Skill Notice
In `harness/delivery/workspace.py` lines 300–304:
```python
if (ws / ".agent").exists() and (ws / ".agent").is_dir():
    legacy_notice = (
        "Legacy '.agent/' directory detected. Run the /psl-harmonize skill "
        "to migrate legacy agents, workflows, and rules to modern '.agents/' structure."
    )
```
The notice directs users to the deprecated `/psl-harmonize` skill rather than the official CLI command `agyis harmonize`.

---

### 3.6 Git Hygiene Exclusion Contamination & Git Blindness

#### A. Git Exclusion Contamination in `constants.py`
In `harness/delivery/constants.py` lines 49–55:
```python
GIT_EXCLUDE_PATTERNS: tuple[str, ...] = (
    ".agents/",
    ".agyis/",
    ".psl/",
    ".cache/",
    "scratch/",
)
```
Line 50 excludes the entire `.agents/` folder.
If `configure_git_exclude(ws)` is run or if a repository inherits this pattern in `.git/info/exclude` or `.gitignore`, `.agents/skills/` and `.agents/rules/` are ignored by git.
This defect materialized directly in `Jasper` (`.gitignore:48:.agents/*`) and `jasper-hosted` (`.git/info/exclude`), hiding version-controlled skills until workers manually intervened.
Conversely, if `.agents/` is un-excluded without explicitly excluding `.agents/archive/`, legacy backup tarballs (`.agents/archive/legacy-agent-backup-*.tar.gz`) are staged into git commits during `git add .agents`, bloating git history with large binary archives (Challenger 2 CHAL-02). Therefore, `GIT_EXCLUDE_PATTERNS` must explicitly scope to `(".agents/artifacts/", ".agents/teamwork/", ".agents/archive/")`.

#### B. Dead Git Hygiene Functions
`configure_git_exclude()` and `verify_zero_git_pollution()` in `harness/delivery/git_hygiene.py` are dead code; they are never invoked by `cmd_init`, `cmd_harmonize`, `cmd_install`, or `install_workspace`.

#### C. Total Absence of Git Remote & Fork Awareness
The `harness/` delivery subsystem has zero capability to inspect:
1. Working tree dirtiness or uncommitted modifications.
2. Remote origin vs. fork URLs (e.g. `sakibtamim` upstream vs `kuasha420` fork).
3. GitHub push permissions on remote origin (`viewerPermission`).
4. Active base branch (`develop` vs `main` vs `master`).
5. Auxiliary clones or worktrees (`mm-website-2` vs `mm-website`).
6. Self-referential harness checks (`psl-agy-harness` host detection).

---

### 3.7 Command Overlap Ambiguity: `agyis init` vs. `agyis install -w`

In `harness/commands/install.py` lines 104–106:
```python
if getattr(args, "workspace", None) is not None and args.workspace is not False:
    setattr(args, "path", args.workspace if args.workspace is not True else None)
    return cmd_init(args)
```
`agyis init [path]` and `agyis install --workspace [path]` are duplicate entrypoints with conflicting argument names (`path` vs `--workspace`).
Running `agyis install` inside a repository without `--workspace` attempts to install the global plugin to `~/.gemini/config/plugins/agyis-harness`, causing user and subagent confusion.

---

## 4. Documentation & Developer Experience Gap Analysis (R3)

An exhaustive audit of documentation, modular skills, and CLI output strings reveals widespread nomenclature drift, broken skills guidance, and missing operational runbooks.

---

### 4.1 Residual `psl` vs. `agyis` Nomenclature Drift

#### A. Source Code Docstrings, Banners & Messages
1. **`harness/__init__.py:7`**: States `PSL Harness for Google Antigravity™` instead of `Agyis Harness for Google Antigravity™`.
2. **`harness/commands/__init__.py:7`**: Docstring states `PSL CLI command modules (ADR-014)` instead of `Agyis CLI command modules`.
3. **`harness/commands/install.py:103, 145`**: Docstrings reference `PSL harness` instead of `Agyis harness`.
4. **`harness/commands/status.py:25, 27`**:
   ```python
   print(f" 🐾 PSL Harness for Google Antigravity™ (v{harness.__version__})")
   ```
   Prints legacy paw emoji and `PSL Harness` banner instead of `Agyis Harness`.
5. **`harness/commands/skills.py:115`**: Prints `PSL Modular Skills` instead of `Agyis Modular Skills`.
6. **`harness/commands/subagents.py:103`**: Prints `PSL Active Subagents` instead of `Agyis Active Subagents`.
7. **`harness/commands/remote.py:22`**: Error message outputs `Usage: psl remote <exec|script|triage|socket> ...` instead of `agyis remote`.
8. **`harness/commands/auth.py:135`**: Prints `PSL Telemetry Authentication Status`.
9. **`harness/delivery/__init__.py:7`, `installer.py:7`, `copy_install.py:7`**: Docstrings state `PSL Harness Delivery`.
10. **`harness/rules/AGENTS.md:83`**: Documents only `PSL_HARNESS_STATE_DIR`, failing to specify primary `AGYIS_HARNESS_STATE_DIR`.

#### B. Documentation Specification Drift
1. **`docs/official-specs/plugin-manifest.md:30-32`**: Contains stale manifest JSON (`"name": "psl-agy-harness"`, `"displayName": "PSL Harness for Google Antigravity™"`, `"version": "0.1.0"`). Real manifest in `plugin.json` is `"name": "agyis-harness"`, `"version": "1.0.0-rc1"`.
2. **`docs/official-specs/custom-agents.md`**: Lines 14, 278, 312 reference `psl-agy-harness`. Line 270 references legacy personas `harness_builder` and `harness_auditor`. Lines 284–295 prescribe `python3 -m harness.cli agents` instead of `agyis agents`.
3. **Sibling Runbook Path Inconsistencies**: `docs/runbooks/knot-mesh-telemetry-fleet-sync.md:58` commands `cd ~/Dev/psl-agy-harness`, while `docs/runbooks/developer-telemetry-onboarding.md:47` commands `git clone ... ~/Dev/agyis-harness`.

---

### 4.2 Modular Skills Documentation Drift & Broken Guidance

#### A. Severe Drift in `psl-harmonize/SKILL.md`
Inspecting `.agents/skills/psl-harmonize/SKILL.md`:
- **Line 6 & 13**: References `PSL Workspace Harmonization Protocol (psl-harmonize)`.
- **Lines 63–70**: Instructs users/agents to execute manual shell copy loops:
  ```bash
  for wf in .agent/workflows/*.md; do
    skill_name=$(basename "$wf" .md)
    mkdir -p ".agents/skills/$skill_name"
    cp "$wf" ".agents/skills/$skill_name/SKILL.md"
  done
  ```
- **Lines 79–81**: Directly commands inserting **deprecated legacy markers**:
  ```markdown
  <!-- Added by PSL-HARNESS -->
  ... PSL Universal Invariants ...
  <!-- End PSL-HARNESS -->
  ```
- **Line 87 & 94–98**: Commands running deprecated commands: `psl skills --sync`, `psl install --workspace`, `psl skills`, `psl agents`, `psl status`.
- **CRITICAL GAP**: The skill **never mentions** `agyis harmonize [path]`! It actively teaches agents to execute manual shell loops and inject deprecated tags.

#### B. Path & Persona Drift in `agent-builder/SKILL.md`
- **Line 70**: Promotes legacy persona `psl_main` instead of canonical `agyis_architect`.
- **Lines 76, 112**: References global scope directory as `~/.gemini/antigravity/agents/`. The actual engine discovery path is `~/.gemini/config/agents/` (as codified in `harness/commands/agents.py:159`, `docs/official-specs/custom-agents.md:25`, and `README.md:170`). Any agent saved to `~/.gemini/antigravity/agents/` will never be loaded.
- **Lines 67–96**: Uses verbose `python3 -m harness.cli agents ...` instead of `agyis agents ...`.

#### C. Stale Rules Reference in `subagent-ladder/SKILL.md`
- **Line 55**: Claims the audit checks against the *"5 Ground Rules in AGENTS.md: Rule 1: Zero error swallowing..."*. The canonical invariant rules in `AGENTS.md` contain **8 empirical rules**. Citing 5 rules causes confusion for audit personas (`hammer`).
- **Line 150**: Prescribes `python3 -m harness.cli test` instead of `agyis test`.

#### D. Persistent `python3 -m harness.cli` Invocations
Ten modular skills in `harness/skills/` prescribe verbose `python3 -m harness.cli` instead of the official `agyis` binary:
- `code-review/SKILL.md:29, 51`
- `sec-forensics/SKILL.md:99, 105, 111`
- `mesh-ops/SKILL.md:61, 74, 85, 91, 97`
- `psl-audit-toolkit/SKILL.md:37, 43, 46, 49, 52, 55`
- `milestone-handoff/SKILL.md:32`
- `remote-ops/SKILL.md:55, 59, 65, 73, 86, 99, 108–114`
- `psl-stack-python/SKILL.md:70, 87`
- `psl-test-python/SKILL.md:25`
- `remote-ops/SKILL.md:110`: Prescribes staging files in `/tmp/.psl_remote_*` instead of `/tmp/.agyis_remote_*`.

---

### 4.3 Specifications for 4 Missing Operational Runbooks

Currently, `docs/runbooks/` contains only two runbooks (`developer-telemetry-onboarding.md` and `knot-mesh-telemetry-fleet-sync.md`). Four operational runbooks are completely missing:

```
Missing Runbook Specifications:
1. docs/runbooks/repo-onboarding.md                (7-step canonical onboarding runbook)
2. docs/runbooks/fork-and-upstream-pr.md           (Fork triage, remotes & cross-repo PRs)
3. docs/runbooks/worktree-and-dirty-tree-hygiene.md(Dirty tree triage matrix, patch vs branch)
4. docs/runbooks/workspace-agent-boundaries.md     (Global vs local agent boundaries)
```

#### Runbook 1: `docs/runbooks/repo-onboarding.md`
- **Target Audience**: Developers and AI agents.
- **Content**: Canonical 7-step guide covering:
  1. Pre-flight working tree triage and uncommitted change safeguarding.
  2. Branch creation off active base branch (`chore/agyis-harness-onboarding`).
  3. Running `agyis harmonize [path]` with `--dry-run` and live execution.
  4. Provisioning stack skills (`agyis skills --sync --stack <stack>`).
  5. Configuring git hygiene (`.gitignore` whitelisting).
  6. Executing hermetic native test suites.
  7. Atomic commit, push, and PR creation via `gh pr create`.

#### Runbook 2: `docs/runbooks/fork-and-upstream-pr.md`
- **Target Audience**: Developers and AI agents.
- **Content**: Operational procedures for collaborator repositories:
  1. Detecting remote permissions via `gh repo view --json viewerPermission`.
  2. Configuring personal forks (`gh repo fork --remote=true --remote-name=fork`).
  3. Synchronizing local base branches with upstream tracking.
  4. Pushing feature branches to `fork` remote.
  5. Submitting cross-repository PRs (`gh pr create --repo <upstream> --head <fork-user>:<branch>`).
  6. Dual-fork topology handling (canonical vs experimental fork).

#### Runbook 3: `docs/runbooks/worktree-and-dirty-tree-hygiene.md`
- **Target Audience**: Developers and AI agents.
- **Content**: Decision matrix for safeguarding in-flight modifications:
  1. Decision tree: Case A High-Value WIP (Patch export + safety branch `backup/*`), Case B Ephemeral Experiments (Named stash `git stash push -u`), Case C Build Artifacts (Pruning).
  2. Multi-worktree collision prevention (`git worktree list --porcelain`, `fatal: '<branch>' is already checked out`).
  3. Safe worktree pruning (`git worktree prune -v`).
  4. Recovering from stale `.git/index.lock` files without killing active processes.

#### Runbook 4: `docs/runbooks/workspace-agent-boundaries.md`
- **Target Audience**: Developers, architects, and AI agents.
- **Content**: Architecture guide defining the 3-Tier Customization Hierarchy:
  1. Clarifies the Fleet Repository Bloat anti-pattern (dumping 7 identical agent files across 50 repos).
  2. Codifies the Canonical Scoping Boundary: Global Scope (`~/.gemini/config/plugins/agyis-harness/agents/`) handles standard personas (`agyis_architect`, `executioner`, `hammer`, `auditor`, `planner`, `coordinator`).
  3. Local Scope (`<project>/.agents/agents/`) is reserved strictly for project-unique specialists (e.g. `knot-mesh`'s `swarm_orchestrator.md`).
  4. Prohibits running `agyis agents --sync` during standard repository onboarding.

---

### 4.4 CLI Help Text Normalization & Argument Consistency

- **`harness/cli.py:299` (`init --stack`)**:
  ```python
  help="Stack preset (typescript, node, python, rust, go, systems, shell, audit, all)"
  ```
- **`harness/cli.py:328` (`install --stack`)**:
  ```python
  help="Stack preset for workspace (typescript, python, systems, shell, audit)"
  ```
  `install --stack` omits `node`, `rust`, `go`, and `all` from its help string, even though `install -w` forwards directly to `cmd_init`. The choices must be normalized.

---

## 5. Comprehensive Remediation Specification (R4)

This section provides concrete, implementable specifications for all product, CLI, delivery engine, and documentation remedies.

---

### 5.1 Comprehensive Gap Taxonomy Matrix

| Gap ID | Subsystem | File & Lines | Severity | Issue Description | Required Remedy |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **GAP-01** | Delivery Engine | `harness/delivery/harmonize.py:143-215` | **Critical** | Copy-only migration; zero deletion or archiving of legacy `.agent/`. | Implement 4-phase deprecation: verify migration -> backup tarball -> deterministic 2-step pruning (`git rm -rf .agent` + `shutil.rmtree` for untracked files) -> assert `.agent/` absent. |
| **GAP-02** | CLI Interface | `harness/cli.py:308-315`, `harness/commands/harmonize.py:20-66` | **High** | `harmonize` lacks flags for pruning, backups, and skill provisioning. | Add `--prune-legacy`, `--clean-agent-dir`, `--backup`, `--stack`, and `--skills` flags. |
| **GAP-03** | Delivery Engine | `harness/delivery/harmonize.py:240-270` | **Medium** | Does not rewrite legacy `.agent/` links in user markdown rules. | Add regex link rewriter replacing `.agent/rules/` paths with `.agents/rules/`. |
| **GAP-04** | Skills Engine | `harness/skills/__init__.py:80-125` | **Critical** | `psl-stack-backend` hardcoded into `typescript`, `python`, `node`, `go` presets. | Decouple presets into Multi-Tier Architecture (Language Runtime vs. Architectural Role). |
| **GAP-05** | Skills Engine | `harness/skills/__init__.py:184-209` | **High** | Waterfall detector has `package.json` dominance; blind to shell scripts. | Multi-factor weighted stack detection supporting shell (`*.sh`) and separating JS vs TS. |
| **GAP-06** | Delivery Engine | `harness/delivery/workspace.py:159-170` | **High** | Line 161 has `(ws / "tests").is_dir()`, making line 168 unreachable (`unittest` dead). | Remove `tests/` check from `has_pytest`; support standard `unittest` discovery. |
| **GAP-07** | Delivery Engine | `harness/delivery/workspace.py:138-188` | **Medium** | Python command extraction completely skipped if `pyproject.toml` is absent. | Add fallback inspection for `setup.py`, `setup.cfg`, and `requirements.txt`. |
| **GAP-08** | Delivery Engine | `harness/delivery/constants.py:49-55` | **High** | `.agents/` included in `GIT_EXCLUDE_PATTERNS`, hiding version-controlled skills; omitting `.agents/archive/` causes binary tarballs to be staged. | Restrict exclude pattern to `.agents/artifacts/`, `.agents/teamwork/`, and `.agents/archive/`. Ensure `agyis onboard` automatically configures git exclusion. |
| **GAP-09** | Delivery Engine | `harness/delivery/git_hygiene.py:21-86` | **Medium** | Zero git remote, fork, permission, or uncommitted work awareness. | Implement `GitTopologyProbe` to inspect remotes, viewer permissions, and dirty trees. |
| **GAP-10** | CLI Interface | `harness/commands/install.py:104-106` | **Medium** | `install -w` and `init` duplicate entrypoints; `install` defaults to global. | Clarify `init` for local setup, `install` for global plugin, and introduce unified `onboard`. |
| **GAP-11** | Modular Skills | `.agents/skills/psl-harmonize/SKILL.md` | **Critical** | Teaches manual bash loops, injects legacy `PSL-HARNESS` tags, omits `agyis harmonize`. | Complete overhaul of skill to teach `agyis harmonize` and canonical rules delimiters. |
| **GAP-12** | Modular Skills | `.agents/skills/agent-builder/SKILL.md` | **High** | Promotes legacy `psl_main`, points global scope to wrong directory. | Update persona to `agyis_architect`, correct global directory to `~/.gemini/config/agents/`. |
| **GAP-13** | Documentation | `docs/runbooks/` | **High** | Completely missing runbooks for repo onboarding, forks, dirty trees, and agent boundaries. | Author 4 official operational runbooks in `docs/runbooks/`. |
| **GAP-14** | CLI & Banners | `harness/commands/*.py` | **Medium** | Residual `PSL Harness` banners, paw emoji, and `Usage: psl remote` messages. | Normalize console banners, help strings, and docstrings to `Agyis Harness`. |

---

### 5.2 CLI Command Specifications: `harmonize` Evolution & Unified `onboard`

#### A. Enhanced `agyis harmonize` Command
```text
agyis harmonize [path] [OPTIONS]

ARGUMENTS:
  path                  Target workspace directory (default: current working directory)

OPTIONS:
  --prune-legacy        Safely remove or git-rm legacy .agent/ directory after successful migration
  --clean-agent-dir     Alias for --prune-legacy
  --backup              Create compressed archive of legacy .agent/ before pruning (default: true)
  --backup-dir DIR      Destination for backup archive (default: <workspace>/.agents/archive/)
  --no-backup           Disable archival before pruning
  --stack STACK         Provision stack skills immediately following harmonization
  --skills LIST         Comma-separated list of explicit modular skills to install
  --dry-run             Preview all file operations and deletions without modifying disk
  --json                Output structured machine-readable JSON report
  -h, --help            Show this help message and exit
```

#### B. New Unified `agyis onboard` Command
To eliminate the disconnect where workers had to coordinate `harmonize`, `skills --sync`, git hygiene, and PR creation manually:
```text
agyis onboard [path] [OPTIONS]

ARGUMENTS:
  path                  Target repository path (default: current working directory)

OPTIONS:
  --stack STACK         Stack preset override (typescript, python, rust, go, systems, shell, auto)
  --role ROLE           Architectural role (backend, frontend, fullstack, cli, mobile, library, desktop_gui, media, audio, infra)
  --subproject PATH     Subproject path for localized monorepo onboarding (depth 2 detection default)
  --upstream-remote NAME Explicit upstream canonical remote name (e.g. upstream, canonical, purrfectsoft)
  --skills LIST         Additional modular skills to provision
  --prune-legacy        Prune legacy .agent/ directory after harmonization (default: true)
  --backup              Archive legacy configs before pruning (default: true)
  --create-branch       Create dedicated onboarding branch 'chore/agyis-harness-onboarding' (default: true)
  --base-branch BRANCH  Explicit base branch to branch from (default: auto-detected active/default)
  --push-fork           Automatically fork and push to personal fork if origin is read-only
  --create-pr           Open GitHub Pull Request using 'gh pr create' upon verification
  --dry-run             Preview all actions (git status, rules, skills, PR targets) without mutation
  --json                Output structured JSON summary
  -h, --help            Show this help message and exit
```

---

### 5.3 Legacy Directory Deprecation & Pruning Lifecycle Algorithm

To prevent both data loss and lingering legacy directories, `harmonize_workspace()` will execute an atomic 4-phase deprecation sequence:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 1: SCAN & DRY-RUN VERIFICATION                                        │
│ • Detect .agent/ (agents, workflows, rules, other).                         │
│ • Validate write access to target .agents/ directory.                       │
│ • Compute SHA-256 digests of all source files.                              │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 2: PROGRESSIVE MIGRATION & SYNTHESIS                                  │
│ • Copy .agent/rules/ to .agents/rules/.                                     │
│ • Convert .agent/workflows/*.md to .agents/skills/<name>/SKILL.md.          │
│ • If custom agents exist, copy to .agents/agents/ (respecting global dedupe)│
│ • Rewrite internal references in AGENTS.md (.agent/ -> .agents/).           │
│ • Verify target files exist on disk with identical checksums.               │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 3: ATOMIC SAFETY ARCHIVAL (If --backup is active)                     │
│ • Create directory <workspace>/.agents/archive/.                            │
│ • Ensure .agents/archive/ is excluded from Git via GIT_EXCLUDE_PATTERNS.    │
│   (Auto-inject into .gitignore or .git/info/exclude to prevent binary staging)│
│ • Create tarball: .agents/archive/legacy-agent-backup-<timestamp>.tar.gz    │
│ • Store manifest of all archived files with timestamps & SHA-256 digests.   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 4: CONTROLLED DETERMINISTIC PRUNING (If --prune-legacy is active)     │
│ • Step 1 (Git Index): If .agent/ contains files tracked in Git:             │
│       Execute: git rm -rf .agent                                            │
│ • Step 2 (Disk Sweep): If .agent/ still exists on disk (untracked debris):  │
│       - Record remaining untracked files in backup manifest.                │
│       - Execute: shutil.rmtree(legacy_agent_dir)                            │
│ • Step 3 (Invariant Assertion):                                             │
│       Assert: not legacy_agent_dir.exists()                                 │
│ • Stage changes in Git index atomically.                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Behavioral Contract:
1. **Safety Gate**: If any target file fails checksum verification in Phase 2, Phase 3 and Phase 4 are aborted immediately. The source `.agent/` directory is never modified.
2. **Binary Archive Git Exclusion Invariant**: Archival directory `.agents/archive/` is strictly excluded from Git tracking via `GIT_EXCLUDE_PATTERNS` in `harness/delivery/constants.py`:
   ```python
   GIT_EXCLUDE_PATTERNS: tuple[str, ...] = (
       ".agents/artifacts/",
       ".agents/teamwork/",
       ".agents/archive/",
   )
   ```
   `agyis onboard` and `agyis harmonize` automatically ensure `.agents/archive/` is excluded via `.gitignore` or `.git/info/exclude` to prevent staging binary tarballs into commits and pull requests (mitigating Challenger 2 CHAL-02).
3. **Deterministic Legacy Pruning Sequence**: `git rm -rf .agent` removes all indexed entries from the Git index and working tree, but leaves untracked files (such as local caches, uncommitted notes, or custom configs) behind on disk. The subsequent check detects any lingering directory and invokes `shutil.rmtree(legacy_agent_dir)` after appending any remaining untracked files to the archival manifest, guaranteeing that `not legacy_agent_dir.exists()` holds true and preventing Tier 1 cleanliness test failures (mitigating Challenger 2 CHAL-01).
4. **Dry-Run Fidelity**: When `--dry-run` is specified, Phase 1 through 4 output planned actions with zero disk mutation.

---

### 5.4 Decoupled Multi-Tier Stack Preset Architecture

Language runtimes must be decoupled from architectural roles to prevent polluting client, GUI, and mobile applications with backend database and tenant-isolation skills.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ TIER A: PRIMARY LANGUAGE RUNTIME (Detected via file extensions & manifests) │
├────────────────────────┬────────────────────────────────────────────────────┤
│ • typescript / node    │ psl-stack-typescript, psl-test-node                │
│ • python               │ psl-stack-python, psl-test-python                  │
│ • rust                 │ psl-test-cargo, psl-stack-systems, psl-stack-shell │
│ • go                   │ psl-test-go                                        │
│ • systems              │ psl-stack-systems, psl-stack-shell                 │
│ • shell                │ psl-stack-shell                                    │
└────────────────────────┴──────────────────────────┬─────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ TIER B: ARCHITECTURAL ROLE (Detected via domain dependencies or explicit)   │
├────────────────────────┬────────────────────────────────────────────────────┤
│ • backend              │ psl-stack-backend, db-ops                          │
│   (Criteria: prisma, typeorm, alembic, sqlalchemy, pg, django, express,     │
│              nest, fastify, docker-compose.yml containing db services)      │
│ • frontend / ui        │ modern-web-guidance                                │
│   (Criteria: react, vue, svelte, next, vite, tailwind, angular)             │
│ • fullstack            │ modern-web-guidance, psl-stack-backend, db-ops      │
│   (Criteria: composite frontend + backend dependencies / fullstack frameworks)│
│ • mobile               │ android-cli                                        │
│   (Criteria: react-native, expo, android/, ios/)                            │
│ • desktop_gui          │ display-ops                                        │
│   (Criteria: electron, tauri, pyqt, pyside, tk)                             │
│ • cli                  │ (No additional role skills)                        │
│ • library              │ (No additional role skills)                        │
│ • media                │ media-ops                                          │
│ • audio                │ audio-ops                                          │
│ • infra                │ mesh-ops, remote-ops, sec-forensics, storage-ops   │
└────────────────────────┴──────────────────────────┬─────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ TIER C: EXPLICIT / ON-DEMAND MODULAR SKILLS (User or Agent Specified)       │
├─────────────────────────────────────────────────────────────────────────────┤
│ storage-ops, audio-ops, sec-forensics, media-ops, mesh-ops, remote-ops,    │
│ git-worktree-ops, subagent-ladder, milestone-handoff, psl-audit-toolkit     │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Proposed Code Structure in `harness/skills/__init__.py`:
```python
LANGUAGE_RUNTIME_PRESETS: Dict[str, List[str]] = {
    "typescript": ["psl-stack-typescript", "psl-test-node"],
    "node": ["psl-stack-typescript", "psl-test-node"],
    "javascript": ["psl-stack-typescript", "psl-test-node"],
    "python": ["psl-stack-python", "psl-test-python"],
    "rust": ["psl-test-cargo", "psl-stack-systems", "psl-stack-shell"],
    "go": ["psl-test-go"],
    "systems": ["psl-stack-systems", "psl-stack-shell"],
    "shell": ["psl-stack-shell"],
}

ARCHITECTURAL_ROLE_PRESETS: Dict[str, List[str]] = {
    "backend": ["psl-stack-backend", "db-ops"],
    "frontend": ["modern-web-guidance"],
    "fullstack": ["modern-web-guidance", "psl-stack-backend", "db-ops"],
    "mobile": ["android-cli"],
    "desktop_gui": ["display-ops"],
    "cli": [],
    "library": [],
    "media": ["media-ops"],
    "audio": ["audio-ops"],
    "infra": ["mesh-ops", "remote-ops", "sec-forensics", "storage-ops"],
}
```

#### Composite Role Resolution & Boundary Presets
1. **Composite Roles**: Modern web applications frequently span presentation and persistence within a unified codebase (e.g. Next.js with Prisma/Postgres, Remix, fullstack TypeScript, Django with modern UI templates). Rather than forcing operators or AI agents to coordinate fragmented CLI invocations, the `fullstack` role synthesizes both frontend (`modern-web-guidance`) and backend (`psl-stack-backend`, `db-ops`) capabilities into an integrated bundle.
2. **Boundary/Terminal Roles**: The roles `cli` and `library` explicitly map to empty lists (`[]`). This eliminates runtime `KeyError` crashes when `--role cli` or `--role library` is passed to the CLI (mitigating Challenger 2 CHAL-03), while guaranteeing that command-line utilities and reusable library packages remain free of extraneous server or database skills.

#### Bounded-Depth Monorepo Workspace Scanning (Depth 2)
A critical failure mode identified in Challenger 2 (CHAL-04) is polyglot monorepo blindness. Modern software repositories frequently employ monorepo orchestrators (Turborepo, pnpm workspaces, Lerna, Nx, Cargo workspaces) where the repository root contains only high-level build configurations (e.g. root `package.json` with `turbo`, `prettier`, `eslint`), while functional services, background workers, and backend APIs reside in nested directories:
- `apps/web/`: Next.js frontend (`package.json` with `next`, `react`)
- `services/api/`: FastAPI backend (`pyproject.toml` with `fastapi`, `sqlalchemy`)
- `services/worker/`: Go background worker (`go.mod`)
- `packages/core/`: Shared Rust / TypeScript libraries

Evaluating only the workspace root causes `detect_workspace_stack()` to match the root `package.json`, incorrectly classifying the entire repository as pure `"typescript"` and omitting Python, Go, and backend architectural skills for worker and API services.

To resolve this without sacrificing the sub-second execution invariant, `detect_workspace_stack()` introduces a **bounded-depth workspace scanner (depth 2)**:

1. **Monorepo Indicator Detection**:
   The scanner first evaluates root-level monorepo markers:
   - Workspace configuration manifests: `pnpm-workspace.yaml`, `turbo.json`, `lerna.json`, `nx.json`.
   - Root `package.json` containing a `"workspaces"` field.
   - Standard multi-package directories: `apps/`, `services/`, `packages/`, `modules/`.

2. **Depth 2 Manifest Sweeping**:
   When monorepo indicators are present, the scanner sweeps immediate child directories at depth 2:
   - `apps/*/package.json`, `apps/*/tsconfig.json` $\rightarrow$ registers `typescript` / `frontend`.
   - `services/*/pyproject.toml`, `services/*/requirements.txt` $\rightarrow$ registers `python` / `backend` (if database dependencies are detected).
   - `services/*/go.mod` $\rightarrow$ registers `go`.
   - `packages/*/Cargo.toml` $\rightarrow$ registers `rust`.

3. **Multi-Runtime & Role Aggregation**:
   Detected language runtimes and architectural roles are aggregated across all discovered subpackages:
   ```python
   def detect_monorepo_stack(workspace_root: Path) -> tuple[set[str], set[str]]:
       detected_languages: set[str] = set()
       detected_roles: set[str] = set()
       for parent in ["apps", "services", "packages", "modules"]:
           dir_path = workspace_root / parent
           if not dir_path.is_dir():
               continue
           for child in dir_path.iterdir():
               if not child.is_dir():
                   continue
               lang, role = detect_single_project_stack(child)
               if lang:
                   detected_languages.add(lang)
               if role:
                   detected_roles.add(role)
       return detected_languages, detected_roles
   ```
   All corresponding skills from `LANGUAGE_RUNTIME_PRESETS` and `ARCHITECTURAL_ROLE_PRESETS` are merged and deduplicated into the target repository's `.agents/skills/`.

4. **Targeted Subproject Harmonization**:
   For granular microservice onboarding within an enterprise monorepo, `agyis onboard` and `agyis harmonize` accept the `--subproject <path>` argument (e.g. `agyis onboard --subproject services/api`), restricting stack detection, rule generation, and skill provisioning strictly to that subpath.

---

### 5.5 Resilient Fork-Aware Remote Detection & PR Submission Pipeline

To eliminate manual bash scripting and execution failures during repository delivery (such as the `sakibtamim` 403 error, inverted cloned-fork workflows, custom canonical remote names, and unhandled permission roles), Agyis introduces a resilient `GitTopologyProbe`:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Resilient GitTopologyProbe Workflow                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. REMOTES INVENTORY: Query git remote -v.                                  │
│    Detect origin, upstream, fork, and custom remotes (e.g. canonical,       │
│    purrfectsoft), or accept explicit --upstream-remote <name>.              │
│                                                                             │
│ 2. TOPOLOGY CLASSIFICATION:                                                 │
│    • Inverted Cloned Fork Topology:                                         │
│        If origin belongs to current authenticated user (fork) AND an        │
│        upstream canonical remote exists (e.g. upstream, purrfectsoft):      │
│          - Push target : origin                                             │
│          - PR target   : upstream / <base-branch>                           │
│          - PR head     : <current-user>:<feature-branch>                    │
│                                                                             │
│    • Standard Direct / Upstream Topology:                                   │
│        Evaluate permissions on target remote (origin or --upstream-remote)  │
│        via GitHub GraphQL:                                                  │
│        gh repo view <target-repo> --json viewerPermission,defaultBranchRef  │
│                                                                             │
│        CASE A: PUSH PERMITTED (Direct Collaborator / Maintainer)            │
│        viewerPermission in ["ADMIN", "MAINTAIN", "WRITE"]:                  │
│          - Push target : target remote (origin / canonical)                 │
│          - PR target   : target remote / <base-branch>                      │
│                                                                             │
│        CASE B: PUSH FORBIDDEN (Fork Required)                               │
│        viewerPermission in ["READ", "TRIAGE", "NONE"]:                      │
│          - Check if personal fork exists:                                   │
│              gh repo view <current-user>/<repo-name>                        │
│              IF NOT FOUND:                                                  │
│                  gh repo fork <target-repo> --clone=false --remote=true \   │
│                                             --remote-name=fork              │
│          - Push target : fork                                               │
│          - PR command  : gh pr create --repo <target-repo>                  │
│                                       --base <base-branch>                  │
│                                       --head <current-user>:<feature-branch>│
│                                                                             │
│ 3. OFFLINE & NON-GITHUB FALLBACK:                                           │
│    If gh CLI is missing (exit 127), unauthenticated, or remote URL is       │
│    non-GitHub (GitLab, Bitbucket, self-hosted Gitea, SSH path):             │
│      - Execute standard: git push -u <remote> <feature-branch>              │
│      - Output non-blocking diagnostic with manual PR/MR instructions.       │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Key Resilience Guarantees:
1. **Inverted Remote Handling**: Developers frequently clone their personal fork as `origin` and add the parent repository as `upstream`. Standard scripts checking permissions on `origin` see `viewerPermission: ADMIN` and naively open PRs against the developer's own fork rather than upstream (as reproduced in Challenger 2 CHAL-05). `GitTopologyProbe` detects when `origin` belongs to the authenticated user and an upstream canonical remote exists, correctly targeting pushes to `origin` and PR submission against `upstream`.
2. **Custom Canonical Remote Support**: In multi-remote setups (e.g. `purrmission`, where the canonical remote is named `purrfectsoft` alongside `origin`), the probe resolves the canonical upstream by:
   - Reading the explicit `--upstream-remote <name>` flag if provided.
   - Scanning remote URLs against known organization naming patterns.
   - Prompting or falling back deterministically without aborting.
3. **Comprehensive Permission Enumeration**: GitHub's GraphQL API defines distinct permissions: `ADMIN`, `MAINTAIN`, `WRITE`, `TRIAGE`, `READ`, `NONE`. Earlier naive logic checked only `ADMIN` vs `READ`, causing crashes on team accounts (`MAINTAIN` members have push rights but failed; `TRIAGE` members do not have push rights but were unhandled). The resilient probe groups permissions into two deterministic sets:
   - **Push Allowed**: `viewerPermission in ["ADMIN", "MAINTAIN", "WRITE"]`.
   - **Fork Required**: `viewerPermission in ["READ", "TRIAGE", "NONE"]`.
4. **Terminal Non-Interactive Safety (`--clone=false`)**: When auto-forking via `gh repo fork`, omitting `--clone=false` triggers an interactive prompt (`"Would you like to clone the fork? [Y/n]"`), hanging headless subagents on stdin. The probe strictly enforces `gh repo fork <repo> --clone=false --remote=true --remote-name=fork`.
5. **Offline & Non-GitHub Fallback**: If `gh` is uninstalled or remotes point to non-GitHub platforms, `GitTopologyProbe` avoids exit-code panics, pushing to the configured remote and outputting clean manual pull request instructions.

#### Auxiliary Clone & Worktree Discrimination:
The probe evaluates `.git` to prevent operating on duplicate clones:
1. If `.git` is a regular file containing `gitdir: <path>`, the directory is an **auxiliary worktree**.
2. If another directory shares the identical remote origin URL and is checked out on the active branch, the directory is an **auxiliary clone**.
3. Auxiliary worktrees and clones are flagged and exempted from duplicate PR generation.

---

### 5.6 Documentation & Modular Skills Remediation Plan

#### Phase 1 (P0): Critical Skill Repairs & Runbooks
1. **Rewrite `.agents/skills/psl-harmonize/SKILL.md`**: Replace manual copy loops with `agyis harmonize [path] --prune-legacy`, replace `PSL-HARNESS` with `AGYIS-HARNESS`, and document verification.
2. **Fix `.agents/skills/agent-builder/SKILL.md`**: Update persona to `agyis_architect`, correct global directory path to `~/.gemini/config/agents/`, use `agyis agents` CLI syntax.
3. **Publish `docs/runbooks/repo-onboarding.md`**: 7-step canonical onboarding runbook.
4. **Publish `docs/runbooks/fork-and-upstream-pr.md`**: Fork and cross-repo PR runbook.

#### Phase 2 (P1): Operational Runbooks & Nomenclature Normalization
1. **Publish `docs/runbooks/worktree-and-dirty-tree-hygiene.md`**: Uncommitted work safeguarding, backup branches, stash triage.
2. **Publish `docs/runbooks/workspace-agent-boundaries.md`**: Global vs local agent boundaries and anti-bloat rules.
3. **Align `docs/official-specs/plugin-manifest.md`**: Update version to `1.0.0-rc1`, name to `agyis-harness`.
4. **Align `subagent-ladder/SKILL.md`**: Update "5 Ground Rules" reference to 8 empirical rules in `AGENTS.md`.
5. **Normalize 10 modular skills**: Replace `python3 -m harness.cli` with `agyis`.

#### Phase 3 (P2): CLI Banners & Docstrings
1. Update `harness/commands/status.py` console banner to `Agyis Harness` (remove legacy paw emoji).
2. Align docstrings across `harness/__init__.py`, `harness/commands/*.py`, and `harness/delivery/*.py`.
3. Normalize `--stack` help strings in `harness/cli.py`.

---

## 6. Draft Architecture Decision Record (ADR-031)

<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# ADR-031: Unified Workspace Harmonization Lifecycle, Multi-Tier Stack Presets, and Fork-Aware Remote Delivery

* **Status**: Proposed / Ready for Implementation
* **Date**: 2026-10-13
* **Authors**: Arafat Zahan (@kuasha420), Agyis Lead Architecture Working Group
* **Corporate Stewardship**: Purrfect Software Limited (PSL)
* **Governed by**: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)
* **Scope**: `harness/`, `docs/`, `.agents/skills/`, `plugin.json`
* **Related ADRs**: ADR-014 (Product vs Project Bifurcation), ADR-015 (Clean-Room Testing), ADR-017 (Progressive Stack Disclosure), ADR-026 (Custom Agents), ADR-030 (Global Plugin Delivery)

---

### Context & Problem Statement

During the 2026 fleet onboarding campaign across 18 repositories (`purrfectsoft`, `kuasha420`, `sakibtamim`), autonomous agents achieved 100% preservation of invariant rules and opened 17 valid GitHub PRs. However, execution required significant manual intervention and ad-hoc scripting due to architectural limitations in the Agyis product:
1. `agyis harmonize` performed a passive copy of legacy files from `.agent/` to `.agents/` without providing any mechanism to prune, archive, or stage the removal of the obsolete `.agent/` directory, causing test suite failures and worker divergence.
2. `STACK_PRESETS` in `harness/skills/__init__.py` hardcoded `psl-stack-backend` into all TypeScript, Python, Node, and Go presets, conflating language runtimes with backend architectural roles and polluting frontend, mobile, and GUI codebases with database migration skills.
3. The delivery engine possessed no awareness of git remotes, permission levels (`viewerPermission`), or forks, failing with HTTP 403 errors when operating on upstream collaborator repositories.
4. Modular skills and documentation suffered from nomenclature drift (`PSL` vs `Agyis`, `python3 -m harness.cli` vs `agyis`), broken skill guidance (`psl-harmonize` commanding manual bash loops and deprecated tags), and missing operational runbooks.

---

### Decision Drivers

1. **Deterministic Cleanliness**: Codebases must transition from legacy `.agent/` to modern `.agents/` with zero lingering debris and zero split-brain configuration states.
2. **Domain Purity**: Skills installed into a repository must reflect its genuine technology stack and architectural role, preventing backend database skills from polluting frontend codebases.
3. **Automated Collaborator Workflows**: The harness must seamlessly handle collaborator repositories, detecting missing write permissions and orchestrating fork-based PRs without manual operator intervention.
4. **Ergonomic Cohesion**: Developers and AI agents must have a single, unified entrypoint (`agyis onboard` / `agyis harmonize --prune-legacy`) for repository onboarding.
5. **Zero-Loss Guarantee**: Uncommitted local work, dirty working trees, and legacy rule files must be safeguarded with verifiable backup mechanisms before any destructive operations are performed.

---

### Considered Options

* **Option 1: Status Quo with External Shell Scripts**:
  Rely on external wrapper scripts (like `heal_fleet.py` and manual bash commands) to delete `.agent/`, copy skills, and handle forks outside the harness.
  * *Rejected*: Undermines the core mission of Agyis as a self-healing autonomous runtime; forces subagents to guess git workflows and risks data loss.
* **Option 2: Script-Only Verification Fixes**:
  Relax verification tests in `verify_fleet.py` to tolerate the continued presence of `.agent/` and omit `psl-stack-backend`.
  * *Rejected*: Solves only the test symptom; leaves repositories in an unclean split-brain state with dual rule directories.
* **Option 3: Unified Architectural Harmonization & Decoupled Presets in Harness Core** (Chosen):
  Implement an atomic 4-phase deprecation lifecycle in `harness/delivery/harmonize.py`, decouple stack presets into Multi-Tier Language and Role presets, introduce native `GitTopologyProbe` for fork-aware delivery, and overhaul documentation and skills.

---

### Decision Outcome

We will adopt **Option 3**. The Agyis harness core will be enhanced with:
1. **Atomic Harmonization Deprecation Lifecycle & Deterministic Pruning**:
   `agyis harmonize` will support `--prune-legacy` (with `--clean-agent-dir` alias), `--backup` (default: true), and `--backup-dir`. Migration will verify target file checksums before archiving to `.agents/archive/` and staging removal via a deterministic two-step sequence: execute `git rm -rf .agent` for git-tracked files, followed by disk detection and `shutil.rmtree(legacy_agent_dir)` for any untracked debris (recording untracked files in the backup manifest), concluding with an explicit assertion that `not legacy_agent_dir.exists()`. Archival directory `.agents/archive/` is added to `GIT_EXCLUDE_PATTERNS` and automatically excluded in `.gitignore` or `.git/info/exclude` to prevent binary tarball pollution into commits.
2. **Multi-Tier Stack Presets, Composite Roles, and Monorepo Scanning**:
   Decouple `STACK_PRESETS` into **Tier A Language Runtimes** (`typescript`, `python`, `rust`, `go`, `systems`, `shell`) and **Tier B Architectural Roles** (`backend`, `frontend`, `fullstack`, `mobile`, `desktop_gui`, `cli`, `library`, `media`, `audio`, `infra`). `psl-stack-backend` is strictly reserved for `backend` and composite `fullstack` roles. Composite role resolution allows `fullstack` to synthesize frontend and backend capabilities (`modern-web-guidance`, `psl-stack-backend`, `db-ops`), while boundary roles (`cli`, `library`) map safely to empty presets `[]` to eliminate `KeyError` crashes. Furthermore, `detect_workspace_stack()` incorporates a bounded-depth monorepo workspace scanner (depth 2) sweeping `apps/`, `services/`, `packages/`, and `modules/` to aggregate language runtimes and roles across polyglot microservices, with support for targeted localized onboarding via `--subproject <path>`.
3. **Resilient Git Topology & Fork-Aware Delivery**:
   Introduce `GitTopologyProbe` in `harness/delivery/` to inspect remotes, identify canonical upstreams via `--upstream-remote <name>` or URL heuristics, handle inverted remote setups (pushing to personal fork `origin` while opening PR against canonical `upstream`), evaluate expanded GitHub permissions (`ADMIN`, `MAINTAIN`, `WRITE` for direct push access vs `READ`, `TRIAGE`, `NONE` for fork-required paths), invoke `gh repo fork --clone=false` non-interactively to prevent stdin terminal hangs, and gracefully fallback to standard git pushes with manual instructions on offline or non-GitHub hosts.
4. **Unified `agyis onboard` Command**:
   Introduce a single CLI command combining working tree hygiene, harmonization, deterministic pruning, multi-tier skill provisioning, monorepo subproject targeting (`--subproject`), custom upstream routing (`--upstream-remote`), branch isolation, and resilient PR creation.
5. **Documentation & Skills Standardization**:
   Overhaul `.agents/skills/psl-harmonize/SKILL.md`, `agent-builder/SKILL.md`, and `subagent-ladder/SKILL.md`. Publish four canonical runbooks in `docs/runbooks/` and normalize all CLI banners and strings to `Agyis Harness`.

---

### Pros and Cons

#### Pros
- **Zero Split-Brain & Zero Residual Debris**: Repositories cleanly transition to `.agents/` without obsolete `.agent/` directories or lingering untracked debris on disk, satisfying strict cleanliness invariants.
- **Repository History Integrity**: Binary `.tar.gz` backups are strictly excluded via `GIT_EXCLUDE_PATTERNS`, preventing git history bloating.
- **Polyglot Monorepo Fidelity**: Bounded-depth workspace scanning ensures backend and worker microservices receive appropriate language runtimes and roles rather than being masked by root frontend tool configs.
- **Architectural Cleanliness**: Pure UI, CLI, and mobile codebases remain free of backend database and tenant-isolation skills.
- **Autonomous Multi-Org Scale**: AI agents can onboard repositories across organizations (`purrfectsoft`, `sakibtamim`) autonomously without hitting 403 permission deadlocks or terminal stdin hangs, correctly routing PRs across inverted forks and custom remotes.
- **Agent Alignment**: Modular skills instruct agents on canonical CLI commands (`agyis harmonize`, `agyis onboard`) rather than outdated shell hacks.

#### Cons
- **Monorepo Scanning Overhead**: Sweeping child directories at depth 2 adds filesystem I/O; mitigated by bounding traversal depth strictly to 2 and evaluating manifest files only, maintaining the sub-second (<1.0s) execution benchmark.
- **Pruning Risk Mitigation Required**: Deleting `.agent/` requires strict checksum verification and mandatory pre-removal archiving to eliminate data loss risks.
- **Preset Backward Compatibility**: Custom user configurations expecting `psl-stack-backend` in the default `typescript` preset must be guided to specify `--role backend`, `--role fullstack`, or `--skills psl-stack-backend`.

---

### Implementation Plan & Milestones

1. **Milestone 1: Core Delivery Engine & CLI Evolution**
   - Add `--prune-legacy`, `--clean-agent-dir`, `--backup`, `--stack` to `harness/cli.py` and `harness/commands/harmonize.py`.
   - Implement Phase 1–4 verification, backup, and deterministic 2-step pruning (`git rm -rf .agent` + `shutil.rmtree` disk sweep + assert) in `harness/delivery/harmonize.py`.
   - Implement regex user rule link rewriting in `harmonize.py`.
   - Update `constants.py` to scope `GIT_EXCLUDE_PATTERNS` to `(".agents/artifacts/", ".agents/teamwork/", ".agents/archive/")` and automate exclusion injection.
   - Fix unreachable dead code in `workspace.py` line 161/168.
2. **Milestone 2: Multi-Tier Stack Preset Decoupling & Monorepo Scanning**
   - Refactor `harness/skills/__init__.py` to separate `LANGUAGE_RUNTIME_PRESETS` from `ARCHITECTURAL_ROLE_PRESETS` including `fullstack`, `cli`, and `library`.
   - Update `detect_workspace_stack()` with weighted multi-factor scoring, shell script detection, and bounded-depth (depth 2) monorepo workspace scanning.
   - Implement composite role resolution (`fullstack`) and architectural role detection.
3. **Milestone 3: Fork-Aware Delivery & Unified Onboarding**
   - Implement resilient `GitTopologyProbe` in `harness/delivery/git_hygiene.py` with inverted remote routing, `--upstream-remote` support, expanded permission evaluation (`ADMIN`, `MAINTAIN`, `WRITE` vs `READ`, `TRIAGE`, `NONE`), `--clone=false` non-interactive invocation, and offline/non-GitHub fallback.
   - Add `agyis onboard` CLI command with `--subproject` and `--upstream-remote` flags.
4. **Milestone 4: Documentation & Modular Skills Standardization**
   - Rewrite `psl-harmonize/SKILL.md`, `agent-builder/SKILL.md`, and `subagent-ladder/SKILL.md`.
   - Author the 4 operational runbooks in `docs/runbooks/`.
   - Normalize console banners and docstrings across `harness/`.
5. **Milestone 5: Hermetic Test Suite Verification**
   - Author clean-room unit tests asserting deterministic pruning, untracked file cleanup, backup tarball creation, git exclude enforcement, monorepo depth-2 detection, composite presets, and fork/remote topology detection.
   - Assert 100% test pass rate with execution benchmark <2.0s.

---

## 7. Verification & Acceptance Criteria

To independently verify the completeness, forensic accuracy, and architectural fidelity of this specification report:

### 7.1 Empirical Citations Verification
```bash
# 1. Verify Parent transcript commands & emergency heal_fleet.py creation
python3 -c "
import json
with open('/home/kuasha/.gemini/antigravity/brain/f2855e28-fe0d-4f60-8160-2fbe3fdf2b16/.system_generated/logs/transcript.jsonl') as f:
    for i, line in enumerate(f):
        if i in [200, 242, 253, 271, 281, 319, 324]:
            d = json.loads(line)
            print(f'Step {i} [{d.get(\"created_at\")}]: {d.get(\"content\", \"\")[:100]}')
"

# 2. Verify heal_fleet.py execution log and 403 error on purrfect-download-manager
grep -n -C 3 "Permission to sakibtamim" /home/kuasha/.gemini/antigravity/brain/f2855e28-fe0d-4f60-8160-2fbe3fdf2b16/.system_generated/tasks/task-274.log

# 3. Verify worker m3 manual git rm .agent
python3 -c "
import json
with open('/home/kuasha/.gemini/antigravity/brain/c15aa052-bc5a-4f09-b8b5-db788fa10318/.system_generated/logs/transcript.jsonl') as f:
    for i, line in enumerate(f):
        if i in [207, 225, 241, 247, 249]:
            d = json.loads(line)
            tc = d.get('tool_calls', [{}])[0].get('args', {})
            print(f'Step {i}: {tc.get(\"CommandLine\")}')
"
```

### 7.2 Code Audit Verification
```bash
# 1. Inspect STACK_PRESETS hardcoding psl-stack-backend
sed -n '80,95p' /home/kuasha/Dev/psl-agy-harness/harness/skills/__init__.py

# 2. Inspect harmonize lack of pruning logic
grep -En "(rmtree|unlink|remove)" /home/kuasha/Dev/psl-agy-harness/harness/delivery/harmonize.py || echo "Zero deletion logic confirmed."

# 3. Inspect unreachable dead code in workspace.py
sed -n '158,170p' /home/kuasha/Dev/psl-agy-harness/harness/delivery/workspace.py

# 4. Inspect GIT_EXCLUDE_PATTERNS contamination
sed -n '49,55p' /home/kuasha/Dev/psl-agy-harness/harness/delivery/constants.py
```

### 7.3 Documentation Drift Verification
```bash
# 1. Verify psl-harmonize skill drift
grep -n "Added by PSL-HARNESS" .agents/skills/psl-harmonize/SKILL.md

# 2. Verify agent-builder skill wrong global path
grep -n "antigravity/agents" .agents/skills/agent-builder/SKILL.md

# 3. Verify residual PSL banners across commands
grep -n "PSL Harness" harness/commands/status.py harness/__init__.py
```

---
*End of Architectural Specification — Agyis Installation, Harmonization & Fleet Onboarding Gaps (v1.0.0)*
