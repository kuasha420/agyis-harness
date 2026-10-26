<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Agyis Project Ledger & Long-Horizon Knowledge Taxonomy 🧠📚

**Governing Standard**: `PSL-SPEC-2026-COCKPIT-DIRECTOR-001`  
**Operational Regime**: Track C (Long-Horizon Autonomous Engineering)  
**Governing ADRs**: ADR-012 (Artifact-First Planning), ADR-014 (Product vs Project Bifurcation), ADR-015 (Clean-Room Testing Contract), ADR-028 (Cleanroom Reconstruction), ADR-031 (Native Succession Protocol)

This ledger preserves permanent architectural decisions, schema contracts, and verified empirical metrics across compaction checkpoints.

---

## [Phase 20] Harmonized Cockpit Director, Dynamic Subagent Router & File Management Hygiene (Issue #92 & #90)
* **Status**: Completed | **Compaction Date**: 2026-10-26 | **Deliverables**: [GitHub Issue #92](https://github.com/kuasha420/agyis-harness/issues/92) & [GitHub Issue #90](https://github.com/kuasha420/agyis-harness/issues/90)
* **Key Architectural Decisions & Discoveries**:
  - **Dynamic Subagent Router (`harness/subagents/routing.py`)**: Elevated `subagent-ladder` into dynamic multi-mode router supporting 4 execution modes (`LADDER`, `PARALLEL_FANOUT`, `TEAMWORK_DAG`, `BOOST_TOURNAMENT`), 12 Canonical Routing Workflows (A–L), and typed transition payloads (`psl_stage_transition_payload.json`).
  - **Single-Source Skill Deduplication Invariant**: Replaced redundant `.agents/skills/` mirrors with relative symlinks to `../../harness/skills/`, saving ~4,500 tokens/turn. Replaced `subagent-ladder` with a 27-line backward-compatible import shim referencing `subagent-router`.
  - **Flight Director CLI Suite (`harness/commands/cockpit.py`)**: Codified `agyis cockpit status`, `agyis cockpit route <letter|alias>`, `agyis cockpit verify [--allow-dirty]`, and anti-drift write guard warnings on root edits > 3 files.
  - **Automated Checkpoint Retention & Rotation (`harness/delivery/compaction_checkpoint.py`)**: Implemented `prune_stale_checkpoints()` retaining the 5 most recent historical epoch checkpoints + `latest.md`.
  - **Workspace & File Hygiene Suite (`harness/commands/clean.py`)**: Added `agyis clean` CLI (`--checkpoints`, `--worktrees`, `--branches`, `--scratch`, `--all`, `--dry-run`, `--json`).
  - **Custodian Living Hygiene Invariant (`agyis_custodian.md`)**: Codified Section 1.5 File Management Hygiene & Scratchpad Gate verifying zero uncommitted scratch files and zero orphaned worktrees before commit gates.
* **Verified Baseline Metrics**:
  - Full test suite: **1,637 hermetic tests passing in 15.08s** (100% green, exit code 0).
  - Sub-second unit modules: `test_clean.py` in 0.038s, `test_cockpit_director.py` in 0.140s, `test_skills.py` in 0.106s, `test_anti_drift.py` in 0.015s, `test_compaction_checkpoint.py` in 0.503s.
  - Closed & verified GitHub issues: #92, #90.
* **Reference Assets Committed**:
  - Core Modules: `harness/subagents/routing.py`, `harness/commands/cockpit.py`, `harness/commands/clean.py`, `harness/delivery/compaction_checkpoint.py`, `harness/hooks/anti_drift_hook.py`, `harness/cli.py`
  - Skills & Agents: `harness/skills/cockpit-director/SKILL.md`, `harness/skills/subagent-router/SKILL.md`, `harness/skills/subagent-ladder/SKILL.md`, `harness/agents/agyis_custodian.md`
  - Tests: `tests/test_cockpit_director.py`, `tests/test_clean.py`, `tests/test_compaction_checkpoint.py`
  - Deliverable Commits: `73c155d`, `119420d`, `4c44c0a`, `586037b` pushed to `origin/main`.

---

## [Phase 21] Single-Source Rule, Skill & Advisory Deduplication Engine & 3-Tier Precedence Hierarchy (Issue #70 & #71)
* **Status**: Completed | **Compaction Date**: 2026-10-27 | **Deliverables**: [GitHub Issue #70](https://github.com/kuasha420/agyis-harness/issues/70) & [GitHub Issue #71](https://github.com/kuasha420/agyis-harness/issues/71)
* **Key Architectural Decisions & Discoveries**:
  - **8 Canonical Invariant Anchors (`PSL-INV-001` through `PSL-INV-008`)**: Formally codified universal engineering rules with immutable identifiers across Layer 1 (`GLOBAL_AGENTS.md`, global plugin rules) and referenced concisely across all agent personas and skills. Eradicated cognitive collision where Rule 7 previously had conflicting definitions.
  - **Single-Source Rule Engine (`harness/delivery/surfaces.py`)**: Implemented `enforce_single_source_rules()` and `lint_rule_echo()`, exported in `harness/delivery/__init__.py`. Detects and strips duplicate universal rule blocks from workspace rules, preserving project-specific command dictionaries and testing contracts.
  - **Context Bloat Elimination**: Stripped 6,515 redundant characters (~1,630 tokens/turn saved), reducing context bloat by >38% per turn and exceeding the AC4 threshold of >=1,500 tokens.
  - **3-Tier Precedence Hierarchy**: Tier 1 (Global Plugin Core Invariants) -> Tier 2 (Workspace Project Specialization) -> Tier 3 (Subagent Role Invariants).
  - **CLI & Onboarding Integration**: Added `agyis rules` CLI command (`--dedup`, `--lint`) in `harness/commands/rules.py` and wired automatic rule deduplication into `agyis onboard` (step 12b).
* **Verified Baseline Metrics**:
  - Full test suite: **1,623 hermetic tests passing in 15.52s** (100% green, exit code 0).
  - Sub-second unit tests: `tests/test_rule_bifurcation_and_packaging.py` passes 14/14 tests in **0.039s** (<0.05s benchmark SLA).
  - Rule Echo Linter: 69 files scanned, 0 echoes found.
  - Runtime Doctor: 9 OK, 0 missing, 0 outdated.
  - Closed & verified GitHub issues: #70, #71.
* **Reference Assets Committed**:
  - Core Modules: `harness/delivery/surfaces.py`, `harness/commands/rules.py`, `harness/commands/onboard.py`, `harness/cli.py`
  - Rules & Prompts: `GLOBAL_AGENTS.md`, `harness/rules/GLOBAL_AGENTS.md`, `.agents/rules/AGENTS.md`, `harness/rules/AGENTS.md`, `rules/AGENTS.md`, `harness/agents/*.md`, `.agents/agents/*.md`
  - Tests: `tests/test_rule_bifurcation_and_packaging.py`
  - Primary Code Commit: `4960078d7ae3eec8ca5a504fde83d0b3dd485106`

---

## [Phase 22] Telemetry Database Compaction & Historical Raw Argument Pruning Policy (Issue #56)
* **Status**: Completed | **Compaction Date**: 2026-10-27 | **Deliverables**: [GitHub Issue #56](https://github.com/kuasha420/agyis-harness/issues/56)
* **Key Architectural Decisions & Discoveries**:
  - **Historical Raw Argument Pruning (`harness/telemetry/db.py`)**: Implemented `prune_historical_tool_arguments()` supporting SQLite files, `:memory:`, and live connections. Safely nullifies raw `arguments_json` and `arguments_snippet` strings for sessions older than $N$ days while retaining session durations, steps, tool names, error classifications, loop flags, and character length counters.
  - **Physical Disk Reclamation**: Executes SQLite `VACUUM` and `PRAGMA wal_checkpoint(TRUNCATE)` post-pruning. Verified on real telemetry database: 195 sessions eligible, 19,842 rows affected, 14.93 MB pruned.
  - **CLI Command Dispatcher (`harness/commands/audit.py`)**: Added `agyis audit prune --days <N> [--dry-run] [--json] [--db <path>]` with human-readable summary output and automated JSON reporting.
* **Verified Baseline Metrics**:
  - Full test suite: **1,650 hermetic tests passing in 16.39s** (100% green, exit code 0).
  - Sub-second unit tests: `tests/test_audit_prune.py` passes 6/6 tests in **0.047s** (<0.20s benchmark SLA).
  - Closed & verified GitHub issues: #56.
* **Reference Assets Committed**:
  - Core Modules: `harness/telemetry/db.py`, `harness/commands/audit.py`, `harness/cli.py`
  - Tests: `tests/test_audit_prune.py`
  - Primary Code Commit: `4312ed4bd5b6539afd1be57314e046297200b969` (Merged at `0503d66`)

---

## [Phase 23] Swarm Continuity, Zero-Kill Graceful Parking & Disaster Recovery (Issues #65, #76, #75)
* **Status**: Completed | **Compaction Date**: 2026-10-27 | **Deliverables**: [GitHub Issue #65](https://github.com/kuasha420/agyis-harness/issues/65), [GitHub Issue #76](https://github.com/kuasha420/agyis-harness/issues/76), [GitHub Issue #75](https://github.com/kuasha420/agyis-harness/issues/75)
* **Key Architectural Decisions & Discoveries**:
  - **Issue #65 PreToolUse Anti-Kill Guard (`harness/hooks/command_safety_hook.py`)**: Expanded `psl-command-safety-guard` matcher in `hooks.json` to `run_command|manage_task|manage_subagents`. Implemented `check_pause_safety()` and `is_pause_gate_active()` to intercept and block destructive terminations (`manage_subagents(kill/kill_all/cancel)`, `manage_task(kill/cancel)`, shell `kill -9` / `pkill -9`) when pause gate is active (`.agents/artifacts/pause_gate.json` or `PARKED_STATE.md`). Built with strict fail-open safety on malformed JSON or OS read errors.
  - **Issue #76 Zero-Kill Graceful Parking Protocol (`harness/skills/graceful-parking/SKILL.md`)**: Codified the Living Artifact standard and bilateral handshake protocol. Eliminates the "Phantom Pause" failure mode (Session `23c8e88c`) by mandating recursive `[PARK_ACK: <UUID>]` token verification from all active leaf subagents before confirming parked state.
  - **Issue #75 Disaster Recovery Protocol (`harness/skills/powerloss-resume/SKILL.md`)**: Codified the 5-phase crash recovery sequence without destructive git commands (`git checkout .`, `git clean -fd`, `git reset --hard`). Features disk/lock forensics, subagent discovery, non-destructive reactive probing, uncommitted diff backup to `.agents/teamwork/backups/`, and `REPLACEMENT_BRIEF.md` resurrection.
  - **Skills Registry Presets (`harness/skills/__init__.py`)**: Registered `resilience` preset (`powerloss-resume`, `db-ops`, `storage-ops`) and `continuity` preset (`graceful-parking`, `milestone-handoff`, `git-worktree-ops`) in `GROUP_PRESETS`.
* **Verified Baseline Metrics**:
  - Full test suite: **1,657 hermetic tests passing in 15.82s** (100% green, exit code 0).
  - Sub-second unit benchmarks: `test_command_safety_hook.py` & `test_skills.py` (57 tests) passing in **0.131s** (<0.50s SLA).
  - Closed & verified GitHub issues: #65, #76, #75.
* **Reference Assets Committed**:
  - Hooks & Core: `harness/hooks/command_safety_hook.py`, `harness/hooks/hooks.json`, `harness/skills/__init__.py`
  - Skills: `harness/skills/graceful-parking/SKILL.md`, `harness/skills/powerloss-resume/SKILL.md`, `.agents/skills/graceful-parking/SKILL.md`, `.agents/skills/powerloss-resume/SKILL.md`
  - Tests: `tests/test_command_safety_hook.py`, `tests/test_skills.py`, `tests/test_cognitive_resilience_manifest.py`
  - Deliverable Commits: `76781f68fcea5c2c79f4c78b537d1b02da2761d5` (Merged at HEAD)
