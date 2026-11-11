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

**Agyis Harness (`agyis-harness`)** is the autonomous agent runtime harness and immune system for **Google Antigravity™**. It protects everyday coding sessions and multi-agent engineering runs against the highest-frequency failure modes observed in production AI trajectories:

- **Silent Runtime & Shell Failures**: Automatically injects a certified CPython >= 3.12 runtime via `uv`, disables interactive terminal pagers (`PAGER=cat`), and neutralizes benign exit-code-1 returns on standalone `grep`/`diff` probes.
- **Runaway Tool Loops & Background Polling**: Breaks 3+ identical consecutive tool invocations and blocks token-wasting background polling loops.
- **Context Cliffs & Compaction Amnesia**: Tracks active token runway before prompt submission (`PreInvocation`), emits single-shot role-tailored warnings, and serializes structured pre-compaction checkpoints (`cockpit_checkpoint.md`).
- **Premature Completion & Untested Diffs**: Prevents agents from declaring completion while modified code (`code_dirty`) or cleanroom specs (`spec_dirty`) remain unverified.
- **Client Repo Bloat & Legacy Drift**: Onboards repositories in isolated branches with zero rule/skill duplication across global and workspace precedence tiers.

### Three-Tier Precedence Hierarchy
Agyis keeps global capabilities and workspace customizations cleanly separated:
1. **Layer 3 — Workspace Local (`.agents/`)**: Repository-specific stack rules (`AGENTS.md`), local specialist skills, and workspace extension commands.
2. **Layer 2 — User Preferences (`~/.gemini/antigravity/`)**: Personal workstation defaults and user standalone skills (`~/.gemini/config/skills/`).
3. **Layer 1 — Global Plugin (`~/.gemini/config/plugins/agyis-harness/`)**: Immutable Agyis core hooks, global invariants (`GLOBAL_AGENTS.md`), modular ops skills, and specialist agent personas.

---

## 2. Quick Start: Global Installation & Workstation Audit

### Install Across Surfaces
```bash
# Install Agyis globally as a Google Antigravity plugin
agyis install

# Optional: install across all detected IDE/CLI surfaces
agyis install --all-surfaces
```

### Run Workstation Diagnostics (`agyis doctor`)
Verify that your host meets the 3-tier runtime matrix (Python >= 3.12 via `uv`, Node/pnpm, `git`, `gh`, `rg`, `fd`, SSH/mesh tools, and PostgreSQL port availability):

```bash
agyis doctor                 # Audit runtime matrix, hooks, symlinks & port 5432 collisions
agyis doctor --heal          # Safe zero-sudo user-space remediation
agyis doctor --re            # Audit reverse-engineering toolchain (JDK, Ghidra, REA, objdump)
agyis status                 # Show harness health, hooks health, token horizon & active subagents
```

---

## 3. Onboarding & Harmonizing Repositories

### Fresh Project Initialization (`agyis init`)
Scaffold `.agents/` stack skills, tagged rules, and cleanroom ledgers into a new or clean directory:
```bash
agyis init [path] -s python -r cli
```

### Brownfield Golden-Path Onboarding (`agyis onboard`)
Onboard any existing repository atomically (dirty-tree safety backup, branch isolation, stale `.next`/`.turbo`/`node_modules/.cache` purge, 4-phase `.agent/` -> `.agents/` harmonization, duplicate skill/rule pruning, verification, and PR preparation):

```bash
agyis onboard . --create-branch chore/onboard
agyis onboard . --allow-dirty
agyis onboard . --skills db-ops,remote-ops
```

### Cleaning Legacy Configurations (`agyis harmonize`, `skills`, `rules`)
```bash
agyis harmonize . [--dry-run]     # Migrate legacy .agent/ assets into .agents/
agyis skills                      # Inspect active modular skills & triggers
agyis skills --prune-duplicates   # Remove workspace copies that shadow global plugin skills
agyis rules --lint                # Check rule files for formatting and duplicate invariant blocks
agyis rules --dedup               # Deduplicate redundant rule declarations
```

---

## 4. Complete 27-Command CLI Palette

| Command | Aliases | What It Does |
| :--- | :--- | :--- |
| `agyis doctor` | — | Audit host runtimes (`--heal`), RE toolchain (`--re`), or synthetic tests (`--anti-synthetic`) |
| `agyis status` | — | Print harness readiness, hooks status, attention horizon & active subagent health |
| `agyis test` | — | Run hermetic test suite (`--diff`, `--affected`, `--pkg`, `--full`, `--harmonize`) |
| `agyis hook` | — | Invoke any of the 7 lifecycle hooks directly (`command-safety`, `anti-loop`, `compactor`, `completion-fence`, `anti-drift`, `token-proximity`, `pre-invocation`) |
| `agyis verify` | — | Verify cleanroom specifications (`--spec`), obligations, or reconstruction scaffolds (`--scaffold`) |
| `agyis audit` | — | Run empirical telemetry analytics, prune old sessions (`prune`), inspect AFF (`aff`), or certify (`certify`/`verdict`) |
| `agyis rules` | — | Lint (`--lint`) and deduplicate (`--dedup`) global and workspace rules |
| `agyis skills` | — | List active modular skills and prune workspace duplicates (`--prune-duplicates`) |
| `agyis agents` | — | Catalog, inspect, validate, and rehydrate the 8 canonical `agyis_*` personas |
| `agyis subagents` | — | Display live subagent token gauges, step counts, and heartbeat liveness (`--liveness`) |
| `agyis cockpit` | — | Flight director pairing health (`status`), workflow dispatch (`route`), and invariant check (`verify`) |
| `agyis router` | `ladder` | Route multi-agent pipelines across the 12 canonical workflows (`A`–`L`) |
| `agyis checkpoint` | — | Capture and verify compaction checkpoints (`status`, `generate`, `create`, `verify`, `prune`) |
| `agyis clean` | — | Purge stale checkpoints, orphaned git worktrees, scratchpads, and opt-in build caches (`--all`) |
| `agyis re` | — | Cleanroom reverse-engineering suite (`status`, `init`, `patch-rea`, `pre-analyze`, `find`, `decompile`, `pcap`, `disasm`, `xrefs`) |
| `agyis ext` | — | Discover, scaffold, and run project extension commands in `.agents/commands/` (`list`, `run`, `init`) |
| `agyis init` | — | Initialize `.agents/` scaffolding with stack/role presets |
| `agyis harmonize` | — | Migrate legacy `.agent/` configs and tags into modern `.agents/` |
| `agyis onboard` | — | Execute the 10-phase atomic repository onboarding pipeline |
| `agyis install` | — | Install Agyis globally into Google Antigravity plugin directories |
| `agyis uninstall` | — | Cleanly remove global plugin registration without collateral damage |
| `agyis remote` | — | Multiplexed SSH execution (`exec`, `script`, `triage`) and ControlMaster socket hygiene |
| `agyis auth` | — | Authenticate GitHub org access for central telemetry hub synchronization |
| `agyis sync` | — | Synchronize local trajectories to telemetry DB or manage the background daemon (`--service`) |
| `agyis gui` | — | Connect via local CDP WebSocket to unlock Trajectory Debug HUD (`--devtools`, `--no-popup`, `--toggle`) |
| `agyis release-notes` | — | Generate structured release notes from conventional commits |
| `agyis changelog` | `changelogs` | Generate, update, or backfill Keep-a-Changelog entries in `CHANGELOG.md` |

See [docs/official-specs/cli-palette.md](official-specs/cli-palette.md) for every subcommand option and syntax specification.

---

## 5. Lifecycle Hooks at a Glance

Agyis registers **7 deterministic hooks** in `hooks.json` so protection runs automatically without manual intervention:
1. **`psl-command-safety-guard` (`PreToolUse`)**: Injects Python >= 3.12 (`uv`), sets `PAGER=cat`, normalizes `grep`/`diff` exit 1 probes.
2. **`psl-anti-loop-guard` (`PreToolUse`)**: Stops 3+ consecutive identical calls and blocks background log/status polling loops.
3. **`psl-output-compactor` (`PostToolUse`)**: Compacts >2KB command dumps down to essential head/tail snippets + errors.
4. **`psl-stop-verification-fence` (`PreToolUse`/`PostToolUse`/`Stop`)**: Ensures code changes pass tests (`agyis test`) and cleanroom specs pass verification (`agyis verify --spec`) before stopping.
5. **`psl-anti-drift-guard` (`PreToolUse`)**: Enforces Plan-Mode read-only locks (`/plan`, ADR-031A) and blocks read-only auditors (`agyis_auditor`) from mutating files.
6. **`psl-token-proximity-guard` (`PreToolUse`)**: Monitors active session token growth against the 256k attention horizon.
7. **`psl-compaction-advisory` (`PreInvocation`)**: Checks token runway before LLM invocation, enforces the 50-step executioner horizon, and auto-saves `.agents/artifacts/compaction_checkpoint_latest.md` and `cockpit_checkpoint.md` before compaction (ADR-033).

---

## 6. Daily Operator Workflows

### Cockpit & Compaction Succession
```bash
agyis cockpit status              # Inspect flight deck readiness, token usage, subagents & git state
agyis cockpit route rca           # Generate structured Root Cause Analysis transition briefing
agyis checkpoint create           # Save an explicit pre-compaction snapshot before resetting session
agyis clean --all                 # Clean expired checkpoints, orphaned subagent worktrees, and scratch files
```

### Telemetry Hub Sync & Background Daemon
```bash
agyis auth login                  # Authenticate against the telemetry hub
agyis sync                        # Push local session telemetry
agyis sync --service install      # Enable automated systemd user background timer
agyis sync --service status       # Verify daemon health
```

### Antigravity Electron GUI & HUD
```bash
agyis gui                         # Unlock Trajectory Debug View over live CDP WebSocket
agyis gui --toggle                # Toggle the in-situ Trajectory Debug HUD open or closed
agyis gui --devtools              # Print active Chrome Inspect URLs from DevToolsActivePort
```

### Remote Triage & Pre-Analyzed Reverse Engineering
```bash
agyis remote triage <host>        # Run compact (<2KB) multi-component diagnostics over ControlMaster SSH
agyis re init                     # Initialize isolated .dirtyroom/ workspace
agyis re pre-analyze ./target.bin # Run headless Ghidra analysis once and index SQLite symbols
agyis re decompile main           # Sub-2s read-only decompilation without stalling agent turns
```

---

## 7. Troubleshooting

- **Stop Hook Blocks Completion (`Verification Required`)**:
  - Run the project's verification suite (`./agyis test` in `agyis-harness`, or `pnpm test` / `pytest` in client repos) to clear `code_dirty`.
  - If you only edited cleanroom docs under `docs/specs/**`, run `agyis verify --spec` to clear `spec_dirty`.
- **`pyenv` / Python Version Warning in `agyis doctor`**:
  - Run `agyis doctor --heal` so `uv` manages CPython >= 3.12 cleanly; Agyis hooks automatically prioritize `uv`'s Python at runtime.
- **Database Port 5432 Collision**:
  - Run `agyis doctor` to spot conflicting containers, or run `detect_port_collision.py --find-free --rebind --env .env` from the `db-ops` skill.
- **High Per-Turn Context Token Overhead**:
  - Run `agyis skills --prune-duplicates --dry-run` (and remove `--dry-run` once reviewed) plus `agyis rules --dedup` to eliminate global-vs-workspace duplication.
- **Stale Worktrees or Checkpoints After Crashes / Parallel Runs**:
  - Run `agyis clean --checkpoints --worktrees` (or `agyis clean --all`) to safely reclaim worktrees and prune old snapshots.
