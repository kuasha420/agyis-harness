<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Agyis Harness — Canonical User & Operator Guide

**Target Audience**: Engineers, Operators, and Teams Running Google Antigravity™  
**Version**: `1.0.0-rc10` (`2026-11-11`)  
**Primary CLI Entrypoint**: `agyis` (backward-compatible alias: `psl`)  

---

## 1. What Agyis Harness Does

**Agyis Harness (`agyis-harness`)** is the autonomous agent runtime harness and immune system for **Google Antigravity™**. Grounded in [`empirical-baselines.md`](taxonomy/empirical-baselines.md), it protects coding sessions and multi-agent runs deterministically in code:

- **Silent Runtime & Shell Failures**: Injects a certified CPython >= 3.12 runtime via `uv`, disables interactive terminal pagers (`PAGER=cat`), and neutralizes benign exit-code-1 returns on standalone `grep`/`diff` probes.
- **Runaway Tool Loops & Polling**: Breaks 3+ identical consecutive tool invocations and blocks token-wasting `manage_task(status)` / log-tailing polling loops.
- **Context Runway & Compaction Succession**: Monitors the **256k** context window (`180k` amber, `230k` red, `45`-step turn ceiling) before prompt dispatch and serializes checkpoints (`.agents/artifacts/compaction_checkpoint_latest.md` & `cockpit_checkpoint.md`).
- **Premature Completion & Cleanroom Fences**: Blocks stopping until modified source (`code_dirty`) clears `agyis test` or modified cleanroom contracts (`spec_dirty`) clear `agyis verify --spec`.
- **Single-Source Workspace Hygiene**: Onboards repositories on isolated branches without duplicating global rules or skills across precedence tiers.

### Three-Tier Precedence Hierarchy
1. **Layer 3 — Workspace Local (`.agents/`)**: Repository-specific stack rules (`AGENTS.md`), project-only specialist skills/agents, and workspace commands (`agyis ext`).
2. **Layer 2 — User Preferences (`~/.gemini/antigravity/`, `~/.gemini/config/`)**: Personal workstation defaults and user standalone skills (`~/.gemini/config/skills/`).
3. **Layer 1 — Global Plugin (`~/.gemini/config/plugins/agyis-harness/`)**: Core **7** `hooks.json` blocks (**8** `doctor` hook runner checks), `GLOBAL_AGENTS.md`, **30** modular skills (`>100` lines include ToC, `<24,576` B cap), and **8** `agyis_*` agent personas.

---

## 2. Quick Start: Global Installation & Workstation Audit

```bash
# Install Agyis globally as a Google Antigravity plugin (or across all IDE/CLI surfaces)
agyis install
agyis install --all-surfaces

# Audit 3-tier runtime matrix, 8 hook runner checks & port 5432 collisions
agyis doctor
agyis doctor --heal          # Safe zero-sudo user-space remediation (uv CPython >= 3.12)
agyis doctor --re            # Audit reverse-engineering toolchain (JDK, Ghidra, REA, objdump)
agyis status                 # Show harness readiness, hooks, attention horizon & active subagents
```

When REA diagnostics or initialization run, `harness/runtime/healing.py` checks `~/.gemini/config/plugins/agyis-harness/skills/reverse-engineer-anything` (alongside local `rea-agents` packages) before fetching on demand.

---

## 3. Onboarding, Harmonizing & Git Hygiene

- **Greenfield Init**: `agyis init [path] -s python -r cli` scaffolds `.agents/` stack rules, skills, and cleanroom ledgers.
- **Brownfield Golden Path**: `agyis onboard . --create-branch chore/onboard` (supports `--allow-dirty`, `--lang`, `--role`, `--subproject`, `--skills`, `--pr`) handles branch isolation, cache invalidation, 4-phase `.agent/` pruning, single-source skill deduplication, port `5432` checks, and PR creation.
- **Maintenance Commands**: `agyis harmonize . [--dry-run]`, `agyis skills --prune-duplicates`, `agyis rules --lint`, and `agyis rules --dedup`.

For detailed human workflows, see:
- **[Repository Onboarding, Agent Boundaries & Cross-Repo PRs](runbooks/repo-onboarding.md)**
- **[Git, Worktree & Dirty-Tree Hygiene](runbooks/git-and-worktree-hygiene.md)**

---

## 4. Consolidated 28-Command CLI Overview

`agyis` (legacy alias `psl`) registers **28** top-level subcommands (`router` and `ladder` registered separately; `changelog` also accepts `changelogs`):

| Domain | Top-Level Commands (`28`) | Primary Focus |
| :--- | :--- | :--- |
| **Diagnostics & Testing** | `doctor`, `test`, `status` | Host matrix/port audits, hermetic & diff-aware testing, live dashboard |
| **Lifecycle Hooks** | `hook` | Direct protojson execution of lifecycle guards |
| **Cockpit & Subagent Routing** | `cockpit`, `router`, `ladder`, `checkpoint`, `subagents` | Flight direction (`A`–`L`), checkpoints, liveness & context gauges |
| **Workspace & Onboarding** | `init`, `harmonize`, `onboard`, `clean`, `ext` | Scaffolding, `.agent/` pruning, cache/worktree cleanup, `.agents/commands/` |
| **Governance & Discovery** | `rules`, `skills`, `agents` | Rule lint/dedup, 30 modular skills, 8 `agyis_*` personas |
| **Telemetry & AFF Audits** | `audit`, `sync`, `auth` | Transcript mining, AFF fitness checks, hub sync & systemd daemon |
| **Cleanroom & Reverse Eng.** | `verify`, `re` | `docs/specs/` claim verification (`--spec`), ledgers, `.dirtyroom/` Ghidra |
| **Delivery, GUI & Releases** | `install`, `uninstall`, `gui`, `remote`, `release-notes`, `changelog` | Global install, Electron CDP HUD, ControlMaster SSH, changelogs |

Authoritative flags, sub-actions, and exit codes live in **[cli-palette.md](official-specs/cli-palette.md)** and **[platform-surface-mapping.md](official-specs/platform-surface-mapping.md)**.

---

## 5. Lifecycle Hooks & Runtime State

Agyis registers **7** hook blocks in `hooks.json` covering **8** runner targets verified by `agyis doctor`:
- `PreToolUse`: `command-safety`, `anti-loop`, `anti-drift` (plan boundaries + Auditor write-block), `token-proximity`, and `verification-fence` dirty tracking.
- `PostToolUse`: `compactor` (2KB output cap preserving errors) and `post-verification-fence`.
- `PreInvocation`: `pre-invocation` (256k/180k/230k runway & 45-step horizon advisory + checkpoint auto-save).
- `Stop`: `verification-fence` (`code_dirty` vs `spec_dirty` clearance with 2-block anti-deadlock valve).

Hook state persists under `/tmp/agyis_harness_state_{uid}` by default (override via `AGYIS_HARNESS_STATE_DIR` or `PSL_HARNESS_STATE_DIR`). For JSON payload schemas and event contracts, see **[lifecycle-hooks.md](official-specs/lifecycle-hooks.md)** and **[platform-surface-mapping.md](official-specs/platform-surface-mapping.md)**.

---

## 6. Daily Operator Workflows

### Cockpit & Compaction Succession ([cockpit-director.md](official-specs/cockpit-director.md))
```bash
agyis cockpit status              # Inspect flight deck health, tokens, subagents & git state
agyis cockpit route rca           # Generate structured workflow briefing (routes A–L)
agyis checkpoint create           # Save compaction_checkpoint_latest.md & cockpit_checkpoint.md
agyis clean --all                 # Prune expired checkpoints, dead worktrees, branches & scratch
```

### Telemetry Hub & Fleet Sync ([telemetry-and-fleet.md](runbooks/telemetry-and-fleet.md))
```bash
agyis auth login --gh --endpoint <telemetry-hub-url>
agyis audit extract && agyis sync
agyis sync --service install && agyis sync --service status
```

### Cleanroom Specs, RE & Antigravity GUI
```bash
agyis verify --spec               # Verify 3 cleanroom RE specs (19 evidence rows: 10 SHA-256 ev_* + 9 EV-20261017 checks)
agyis verify                      # Validate .agents/ledger/obligation_ledger.json
agyis re init && agyis re pre-analyze ./target.bin
agyis gui                         # Unlock Trajectory Debug View over CDP WebSocket (--toggle, --devtools)
```

---

## 7. Quick Troubleshooting & Reference Map

- **Stop Hook Blocks Completion**: Run `agyis test` (or native repo tests per [testing-contracts.md](official-specs/testing-contracts.md)) to clear `code_dirty`; run `agyis verify --spec` to clear `spec_dirty` after `docs/specs/` edits.
- **Python / Runtime Warnings**: Run `agyis doctor --heal` to provision CPython >= 3.12 via `uv`.
- **Port 5432 Collisions**: Run `detect_port_collision.py --find-free --rebind --env .env` (see [repo-onboarding.md](runbooks/repo-onboarding.md#6-database-port-5432-collision-check-prisma-p1000)).
- **High Context Overhead**: Run `agyis skills --prune-duplicates` and `agyis rules --dedup`.
- **Stale Worktrees or Index Locks**: Follow [git-and-worktree-hygiene.md](runbooks/git-and-worktree-hygiene.md) (`agyis clean --checkpoints --worktrees`).

**Further Reading**: [ADR Registry](adr/README.md) · [CLI Palette](official-specs/cli-palette.md) · [Lifecycle Hooks](official-specs/lifecycle-hooks.md) · [Cockpit Director](official-specs/cockpit-director.md) · [Platform Surface Mapping](official-specs/platform-surface-mapping.md) · [Testing Contracts](official-specs/testing-contracts.md) · [Empirical Baselines](taxonomy/empirical-baselines.md)
