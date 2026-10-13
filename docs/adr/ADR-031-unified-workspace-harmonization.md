<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# ADR-031: Unified Workspace Harmonization Lifecycle, Multi-Tier Stack Presets, and Fork-Aware Remote Delivery

* **Status**: Accepted
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
   - Implement resilient `GitTopologyProbe` in `harness/delivery/git_topology.py` with inverted remote routing, `--upstream-remote` support, expanded permission evaluation (`ADMIN`, `MAINTAIN`, `WRITE` vs `READ`, `TRIAGE`, `NONE`), `--clone=false` non-interactive invocation, and offline/non-GitHub fallback.
   - Add `agyis onboard` CLI command with `--subproject` and `--upstream-remote` flags.
4. **Milestone 4: Documentation & Modular Skills Standardization**
   - Rewrite `psl-harmonize/SKILL.md`, `agent-builder/SKILL.md`, and `subagent-ladder/SKILL.md`.
   - Author the 4 operational runbooks in `docs/runbooks/`.
   - Normalize console banners and docstrings across `harness/`.
5. **Milestone 5: Hermetic Test Suite Verification**
   - Author clean-room unit tests asserting deterministic pruning, untracked file cleanup, backup tarball creation, git exclude enforcement, monorepo depth-2 detection, composite presets, and fork/remote topology detection.
   - Assert 100% test pass rate with execution benchmark <2.0s.
