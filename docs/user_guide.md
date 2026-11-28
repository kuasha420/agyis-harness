<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Agyis Harness — Canonical User & Operator Guide

**Target Audience**: Engineers, Operators, and Teams Running Google Antigravity™  
**Version**: `1.2.0` (`2026-11-28`)  
**Primary CLI Entrypoint**: `agyis` (backward-compatible alias: `psl`)  

---

## 1. What Agyis Harness Does

**Agyis Harness (`agyis-harness`)** is the autonomous agent runtime harness and immune system for **Google Antigravity™** (`Desktop v2.34.0+`, `agy v1.5.15`, `IDE v2.8.0`). Grounded in [`empirical-baselines.md`](taxonomy/empirical-baselines.md) and **PSL Invariant Codex v2** (`PSL-INV-001`–`008` core invariants + on-demand `PSL-RE-001` in `re-ops`), it protects coding sessions and multi-agent runs deterministically in code:

- **Silent Runtime & Shell Failures**: Injects a certified CPython >= 3.12 (`3.14` recommended via `uv`) runtime, disables interactive terminal pagers (`PAGER=cat`, `SYSTEMD_PAGER=cat`), and neutralizes benign exit-code-1 returns on standalone `grep`/`rg`/`diff` probes.
- **Runaway Tool Loops & Polling**: Breaks 3+ identical consecutive tool invocations and blocks token-wasting `manage_task(status)` / log-tailing polling loops.
- **Context Runway & Compaction Succession**: Dynamically scales across **Gemini 4 (`gemini-4-neon`, `gemini-4-hydrogen`, `512k`/`1M`)** and **`256k`** context windows (`70%` amber, `90%` red, `80`-step soft checkpoint horizon), emitting `v2.34.0+` nested `systemMessage` advisories and serializing CID-scoped checkpoints (`.agents/artifacts/checkpoints/<conv_id>.md`).
- **Premature Completion & Cleanroom Fences**: Blocks stopping until modified source (`code_dirty`) clears `agyis test` or modified cleanroom contracts (`spec_dirty`) clear `agyis verify --spec`.
- **Single-Source Workspace Hygiene**: Onboards repositories on isolated branches without duplicating global rules, skills, or agents across precedence tiers.

### Three-Tier Precedence Hierarchy
1. **Layer 3 — Workspace Local (`.agents/`)**: Repository-specific stack rules (`AGENTS.md`), project-only specialist skills/agents, and workspace commands (`agyis ext`).
2. **Layer 2 — User Preferences (`~/.gemini/antigravity/`, `~/.gemini/config/`)**: Personal workstation defaults and user standalone skills (`~/.gemini/config/skills/`).
3. **Layer 1 — Global Plugin (`~/.gemini/config/plugins/agyis-harness/`)**: Core **7** `hooks.json` blocks (**8** `doctor` hook runner checks), `GLOBAL_AGENTS.md` (Codex v2), **33** modular skills (`>100` lines include ToC, `<24,576` B cap), and **8** `agyis_*` agent personas (`<=20` canonical `v2.34+` tools).

---

## 2. Quick Start: Global Installation & Workstation Audit

```bash
# Install Agyis globally as a frozen wheel across all Antigravity surfaces
agyis install --global --wheel --all-surfaces
# Optional: enable CDP DevTools desktop launcher & auto-unlock HUD service
agyis gui --install-launcher
# Restart Antigravity from your desktop launcher after `--install-launcher`
# so the single-instance Electron process launches with `--remote-debugging-port=0`.
agyis gui --service install

# Audit 3-tier runtime matrix, engines/packageManager constraints, 8 hook runner checks & port 5432 collisions
agyis doctor
agyis doctor --heal          # Safe zero-sudo user-space remediation (uv CPython 3.14 recommended / >= 3.12)
agyis doctor --re            # Audit reverse-engineering toolchain (JDK, Ghidra, REA, objdump)
agyis status                 # Show harness readiness, hooks, attention horizon & active subagents
```

When REA diagnostics or initialization run, `harness/runtime/healing.py` checks both `<config_dir>/skills/reverse-engineer-anything` and `~/.gemini/config/plugins/agyis-harness/skills/reverse-engineer-anything` (alongside local `rea-agents` packages) before fetching on demand, preventing duplicate workspace provisioning.

---

## 3. Onboarding, Harmonizing & Git Hygiene

- **Greenfield Init**: `agyis init [path] -s python -r cli` scaffolds `.agents/` stack rules, skills, and cleanroom ledgers.
- **Brownfield Golden Path**: `agyis onboard . --create-branch chore/onboard` (supports `--allow-dirty`, `--ensure-project`, `--lang`, `--role`, `--subproject`, `--skills`, `--pr`) handles branch isolation, `git ls-files`-safe cache invalidation, 4-phase `.agent/` pruning with full `.agent/` link rewriting, slim Prettier-clean `AGENTS.md` injection (relocating custom project sections safely), non-mutating `.agyis/test_manifest.json` generation, `engines`/`packageManager` preflight, single-source skill deduplication, port `5432` checks, and PR creation.
- **Project Registry & Maintenance Commands**: `agyis project list`, `agyis project ensure [path] [--dry-run]`, `agyis harmonize . [--dry-run]`, `agyis skills --prune-duplicates`, `agyis rules --lint`, and `agyis rules --dedup`.

For detailed human workflows, see:
- **[Repository Onboarding, Agent Boundaries & Cross-Repo PRs](runbooks/repo-onboarding.md)**
- **[Git, Worktree & Dirty-Tree Hygiene](runbooks/git-and-worktree-hygiene.md)**

---

## 4. Consolidated 31-Command CLI Overview

`agyis` (legacy alias `psl`) registers **31** logical top-level subcommands (`32` parser entries including `crosstalk`, `project`, `release` & `changelogs` alias; `router` and `ladder` registered separately):

| Domain | Top-Level Commands (`31`) | Primary Focus |
| :--- | :--- | :--- |
| **Diagnostics & Testing** | `doctor`, `test`, `status` | Host matrix/`engines`/port audits, hermetic & diff-aware testing, live dashboard |
| **Lifecycle Hooks** | `hook` | Direct protojson execution of lifecycle guards |
| **Cockpit & Subagent Routing** | `cockpit`, `router`, `ladder`, `checkpoint`, `subagents`, `crosstalk` | Flight direction (`A`–`L`), checkpoints, liveness, context gauges & cross-project batons |
| **Workspace & Onboarding** | `init`, `harmonize`, `onboard`, `project`, `clean`, `ext` | Scaffolding, `.agent/` pruning, `projects/*.json` registry, cache/worktree cleanup, `.agents/commands/` |
| **Governance & Discovery** | `rules`, `skills`, `agents` | Rule lint/dedup, 33 modular skills (incl. `crosstalk`, `pause`, `resume`), 8 `agyis_*` personas |
| **Telemetry & AFF Audits** | `audit`, `sync`, `auth` | Transcript mining, AFF fitness checks, hub sync & systemd daemon |
| **Cleanroom & Reverse Eng.** | `verify`, `re` | `docs/specs/` claim verification (`--spec`), ledgers, `.dirtyroom/` Ghidra |
| **Delivery, GUI & Releases** | `install`, `uninstall`, `gui`, `remote`, `release`, `release-notes`, `changelog` | Global install, Electron CDP HUD, ControlMaster SSH, atomic release bump & changelogs |

Authoritative flags, sub-actions, and exit codes live in **[cli-palette.md](official-specs/cli-palette.md)** and **[platform-surface-mapping.md](official-specs/platform-surface-mapping.md)**.

---

## 5. Lifecycle Hooks & Runtime State

Agyis registers **7** hook blocks in `hooks.json` covering **8** runner targets verified by `agyis doctor`:
- `PreToolUse`: `command-safety` (CPython `>=3.12` / `3.14` recommended, `#101` POSIX quote-aware inline script promotion, eager/lazy MCP normalization, `/swarm` pause guard, `#93` anti-clobber guard, `#67` memory/concurrency semaphore), `anti-loop`, `anti-drift` (plan boundaries, `#94` static `*PLAN*.md` exclusion, `#93` anti-clobber, Auditor write-block, Q5 read-only shell guard), `token-proximity` (`resolve_display_velocity_tier` `<25%` fill burn-rate gate), and `verification-fence` dirty tracking.
- `PostToolUse`: `compactor` (`overwriteResult` on `>2KB` succeeding `run_command` & `>32KB` `read_file`, 100% verbatim on errors) and `post-verification-fence`.
- `PreInvocation`: `pre-invocation` (scaled `256k`/`512k`/`1M` runway, window-scaled checkpoint step horizon `80`/`160`/`320`, and `systemMessage` advisories + checkpoint auto-save).
- `Stop`: `verification-fence` (`code_dirty` vs `spec_dirty` clearance with `continuationActive` awareness, native `invoke_subagent` Stop-Gate truth & 2-block anti-deadlock valve).

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

### Telemetry Hub & Fleet Sync (Optional Self-Hosted Hub — [telemetry-and-fleet.md](runbooks/telemetry-and-fleet.md))
```bash
# Local transcript mining works standalone with zero remote hub:
agyis audit extract

# Optional: authenticate only when syncing across devices via a self-hosted/team hub
agyis auth login --gh --endpoint <telemetry-hub-url>
agyis sync
agyis sync --service install && agyis sync --service status
```

### Cleanroom Specs, RE & Antigravity GUI
```bash
agyis verify --spec               # Verify 4 cleanroom RE specs (including v2.34.0 drift inventory)
agyis verify                      # Validate .agents/ledger/{obligation_ledger.json,obligations.json} (rea@6.9.0 schema)
agyis re init && agyis re pre-analyze ./target.bin
agyis re addr 0x401000 --binary ./target.bin # Inspect PE32/PE32+ & Linux ELF64/ELF32 addresses/symbols
agyis re patch-rea --apply        # Apply zero-copy direct mount patch (bypasses 1.3GB disk clone)
agyis re seed --pcap session.pcap # Ingest network packets into SQLite and link to runs
agyis re daemon start             # Launch persistent REA MCP bridge supervisor (<0.8s queries)
agyis re prime --top 25           # Pre-warm decompiler query cache on priority functions
agyis re cache status             # Inspect decompiler query cache (<5ms responses, --json supported)
agyis re clean                    # Safely purge orphan Ghidra locks, prune logs, and vacuum DB
agyis gui --install-launcher      # Install opt-in CDP desktop launcher override (--remote-debugging-port=0)
agyis gui                         # Unlock Trajectory Debug HUD over CDP WebSocket (--toggle, --devtools, --service)
```
*See [dirtyroom-operations.md](runbooks/dirtyroom-operations.md) and the Layer 1 `re-ops` skill (`PSL-RE-001`, `--role re` / `--role cleanroom`) for full preparation, seeding, priming, 4-vector verification, and hygiene lifecycle.*

---

## 7. Quick Troubleshooting & Reference Map

- **Stop Hook Blocks Completion**: Run `agyis test` (or native repo tests per [testing-contracts.md](official-specs/testing-contracts.md)) to clear `code_dirty`; run `agyis verify --spec` to clear `spec_dirty` after `docs/specs/` edits.
- **Python / Runtime Warnings**: Run `agyis doctor --heal` to provision CPython `3.14` (minimum `>= 3.12`) via `uv`.
- **Port 5432 Collisions**: Run `detect_port_collision.py --find-free --rebind --env .env` (see [repo-onboarding.md](runbooks/repo-onboarding.md#6-database-port-5432-collision-check-prisma-p1000)).
- **High Context Overhead**: Run `agyis skills --prune-duplicates` and `agyis rules --dedup`.
- **Stale Worktrees or Index Locks**: Follow [git-and-worktree-hygiene.md](runbooks/git-and-worktree-hygiene.md) (`agyis clean --checkpoints --worktrees`).

**Further Reading**: [ADR Registry](adr/README.md) · [CLI Palette](official-specs/cli-palette.md) · [Lifecycle Hooks](official-specs/lifecycle-hooks.md) · [Cockpit Director](official-specs/cockpit-director.md) · [Platform Surface Mapping](official-specs/platform-surface-mapping.md) · [Testing Contracts](official-specs/testing-contracts.md) · [Empirical Baselines](taxonomy/empirical-baselines.md)
