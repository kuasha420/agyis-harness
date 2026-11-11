<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Agyis Harness — Developer & Architecture Guide

**Target Audience**: Harness Contributors, Maintainers, and Autonomous Agent Architects  
**Version**: `1.0.0-rc10` (`2026-11-11`)  
**Repository**: `agyis-harness` (Package module: `harness`)  

---

## 1. Core Architectural Philosophy: Product vs. Project Bifurcation (ADR-014)

Every module in `agyis-harness` preserves strict physical and logical isolation between **The Product** (distributed globally) and **The Project** (empirical lab, archives, and test suite):

```text
agyis-harness/
├── pyproject.toml            # Zero-dependency standard-library Python package (dependencies = [])
├── plugin.json               # Google Antigravity plugin manifest ("agyis-harness")
├── matrix.json               # 3-Tier Runtime Dependency Matrix (Languages, SWE CLI, Mesh)
├── hooks.json                # Declarative lifecycle hook registrations (7 blocks -> 8 runner targets)
│
├── harness/                  # [THE PRODUCT] Distributable core package
│   ├── cli.py                # Unified 28-command `agyis` CLI dispatcher (`psl` legacy alias)
│   ├── discovery.py          # Global/workspace resource discovery & root path resolution
│   ├── agents/               # 8 canonical `agyis_*` specialist personas + alias bridge
│   ├── cleanroom/            # Specification, obligation ledger, and REA reconstruction verifiers
│   ├── commands/             # 25 handler modules + __init__.py backing 28 top-level subcommands
│   ├── delivery/             # Installer, harmonizer, onboarder, git topology, checkpoints
│   ├── doctor/               # Modular diagnostics & health check runners
│   ├── gui/                  # Electron CDP WebSocket unlockers & HUD (`assets/` via importlib.resources)
│   ├── harmonize/            # Legacy `.agent/` -> `.agents/` harmonization engine
│   ├── hooks/                # 7 hooks.json blocks (8 doctor hook checks; fail-safe runner)
│   ├── mutation/             # Atomic file mutation & backup/patch helpers
│   ├── re/                   # Cleanroom reverse-engineering & REA integration modules
│   ├── remote/               # ControlMaster SSH multiplexing & compact triage (<2KB)
│   ├── rules/                # Curated agent governance (`GLOBAL_AGENTS.md` vs `AGENTS.md`)
│   ├── runtime/              # Diagnostics, `healing.py` (`agyis-harness` REA path), hygiene checks
│   ├── skills/               # 30 modular skills (`>100` L carry ToC, `<24,576` B cap; `.agents/skills/` symlinks)
│   ├── subagents/            # Routing (`routing.py`), liveness, truth, succession, spec & scaffolding
│   ├── telemetry/            # Session harvester, hub sync client & systemd user daemon
│   └── utils/                # Shared helpers including state (`state.py`) & context metadata (`context.py`)
│
├── pipeline/                 # [THE PROJECT] Telemetry extraction & empirical classification lab
├── data/                     # [THE PROJECT] Local empirical SQLite telemetry store (`telemetry.db`)
├── docs/                     # [THE PROJECT] ADRs, 7 Official Specs, 3 RE Specs, 3 Runbooks, 2 Taxonomy, Archive
└── tests/                    # [THE PROJECT] Hermetic unit, integration, contract & E2E tests
```

### Key Non-Negotiable Architecture Rules
1. **Zero Mandatory External Dependencies (`PSL-INV-011`)**: `harness/` uses **strictly Python 3.12+ standard library**. Never import `pytest`, `requests`, `pydantic`, or `pipeline/` inside `harness/` (enforced by `agyis audit aff`).
2. **Externalized Foreign Assets (`PSL-INV-011`)**: Place browser/UI JS and CSS assets under `harness/gui/assets/` and load via `importlib.resources`, never as raw multiline Python strings.
3. **Hermetic State Isolation (`harness/utils/state.py`)**: Persistent runtime state defaults to `/tmp/agyis_harness_state_{uid}` and honors `AGYIS_HARNESS_STATE_DIR` / `PSL_HARNESS_STATE_DIR` overrides. Tests must inject isolated `tempfile.TemporaryDirectory()` paths.
4. **On-Demand REA Skill Provisioning (`harness/runtime/healing.py`)**: Searches installed `rea-agents` packages and `~/.gemini/config/plugins/agyis-harness/skills/reverse-engineer-anything` rather than vendoring upstream skills in-tree.

---

## 2. Unified 28-Command CLI Architecture (`harness/cli.py`)

`harness/cli.py` registers **28** top-level subparsers (`router` and `ladder` separately, plus `changelogs` alias on `changelog`) backed by 25 modules in `harness/commands/`:

| Domain | Top-Level Subcommands (`28`) | Primary Backing Modules |
| :--- | :--- | :--- |
| **Diagnostics & Testing** | `doctor`, `test`, `status` | `harness/commands/{doctor,test,status}.py`, `harness/runtime/` |
| **Lifecycle Hooks** | `hook` | `harness/commands/hook.py`, `harness/hooks/runner.py` |
| **Cockpit & Routing** | `cockpit`, `router`, `ladder`, `checkpoint`, `subagents` | `harness/commands/{cockpit,checkpoint,subagents}.py`, `harness/subagents/routing.py` |
| **Workspace & Onboarding** | `init`, `harmonize`, `onboard`, `clean`, `ext` | `harness/commands/{init,harmonize,onboard,clean,ext}.py`, `harness/delivery/` |
| **Governance & Discovery** | `rules`, `skills`, `agents` | `harness/commands/{rules,skills,agents}.py`, `harness/subagents/` |
| **Telemetry & AFF Audits** | `audit`, `sync`, `auth` | `harness/commands/{audit,sync,auth}.py`, `harness/telemetry/` |
| **Cleanroom & Reverse Eng.** | `verify`, `re` | `harness/commands/{verify,re}.py`, `harness/cleanroom/`, `harness/re/` |
| **Delivery, GUI & Releases** | `install`, `uninstall`, `gui`, `remote`, `release-notes`, `changelog` | `harness/commands/{install,gui,remote,release_notes,changelog}.py`, `harness/gui/` |

Authoritative flags, sub-actions, and platform boundaries live in [`cli-palette.md`](official-specs/cli-palette.md) and [`platform-surface-mapping.md`](official-specs/platform-surface-mapping.md).

---

## 3. Lifecycle Hooks Architecture (`harness/hooks/`)

[`harness/hooks/hooks.json`](../harness/hooks/hooks.json) declares **7** registration blocks executed via `python3 -m harness.hooks.runner <name>` or `agyis hook <name>`, yielding **8** distinct runner checks verified by `agyis doctor` (`check_hooks_health`):

| Registration ID | Event(s) | Module | Runner Target(s) |
| :--- | :--- | :--- | :--- |
| `psl-anti-drift-guard` | `PreToolUse` | [`anti_drift_hook.py`](../harness/hooks/anti_drift_hook.py) | `anti-drift` |
| `psl-anti-loop-guard` | `PreToolUse` | [`anti_loop_hook.py`](../harness/hooks/anti_loop_hook.py) | `anti-loop` |
| `psl-command-safety-guard` | `PreToolUse` | [`command_safety_hook.py`](../harness/hooks/command_safety_hook.py) | `command-safety` |
| `psl-output-compactor` | `PostToolUse` | [`output_compactor_hook.py`](../harness/hooks/output_compactor_hook.py) | `compactor` |
| `psl-stop-verification-fence` | `PreToolUse`, `PostToolUse`, `Stop` | [`completion_fence_hook.py`](../harness/hooks/completion_fence_hook.py) | `verification-fence`, `post-verification-fence` |
| `psl-token-proximity-guard` | `PreToolUse` | [`token_proximity_guard.py`](../harness/hooks/token_proximity_guard.py) | `token-proximity` |
| `psl-compaction-advisory` | `PreInvocation` | [`pre_invocation_hook.py`](../harness/hooks/pre_invocation_hook.py) | `pre-invocation` |

All hooks fail open on malformed stdin. Full protojson payload contracts, thresholds (`256k` window / `180k` amber / `230k` red / `45`-step turn interrupt), and state machine rules live in [`lifecycle-hooks.md`](official-specs/lifecycle-hooks.md) and [`platform-surface-mapping.md`](official-specs/platform-surface-mapping.md).

---

## 4. Agent Personas, Cockpit Director & Subagent Router

- **8 Canonical `agyis_*` Personas** ([`harness/agents/__init__.py`](../harness/agents/__init__.py)): `agyis_architect`, `agyis_auditor`, `agyis_builder`, `agyis_coordinator`, `agyis_custodian`, `agyis_investigator`, `agyis_planner`, and `agyis_reviewer` (mapped from legacy aliases via `resolve_agent_name()`).
- **Cockpit & Routing**: Root sessions follow [`cockpit-director.md`](official-specs/cockpit-director.md) via `agyis cockpit` and `agyis router` (`agyis ladder`), with checkpoints serialized via `agyis checkpoint`.
- **Custom Agents & Boundary Enforcement**: Frontmatter tool allowlists (`ANTIGRAVITY_PLATFORM_TOOLS`) and workspace boundaries are governed by [`custom-agents.md`](official-specs/custom-agents.md) and [`repo-onboarding.md`](runbooks/repo-onboarding.md).

---

## 5. GUI HUD, Cleanroom Specs & Extensible Workspace CLI

- **Electron CDP HUD (`agyis gui`)**: Assets under `harness/gui/assets/` track SPA routes (`/c/:id`) dynamically and purge stale DOM/style nodes on re-injection (`PSL-INV-010`).
- **Cleanroom Verification (`agyis verify`)**: Validates **3** cleanroom RE specifications (**19** verified empirical evidence rows: `10` SHA-256 `ev_*` digests + `9` `EV-20261017` runtime checks; verified via `agyis verify --spec`) in `docs/specs/` (zero executable code permitted inside `docs/specs/`), and verifies typed `.agents/ledger/obligation_ledger.json` coverage via `agyis verify` (`ADR-028`, `PSL-INV-007`).
- **Dirtyroom Acceleration (`agyis re`) & Extensions (`agyis ext`)**: `.dirtyroom/` Ghidra `-noanalysis -readOnly` queries stay isolated under `PSL-INV-009` ([`rea-antigravity-architecture.md`](official-specs/rea-antigravity-architecture.md)); workspace extensions run inside `.agents/commands/` under `ADR-034`.

---

## 6. Verification Standards, AFF Gate & Contributor Rules

```bash
./agyis test                         # Full hermetic suite (sub-second component modules)
agyis test --diff                    # Diff-aware tests vs working tree (--affected, --pkg)
agyis audit aff                      # Layer boundaries, DAG acyclicity, external assets, bounded caches
agyis doctor                         # 3-tier runtime matrix, 8 hook runner checks, port 5432, symlinks
agyis doctor --anti-synthetic        # Detect tautological / synthetic tests
agyis verify --spec && agyis verify  # Cleanroom specs (19 empirical evidence rows) & obligation ledgers
agyis rules --lint                   # Agent rule echo & formatting audit
agyis audit certify                  # Out-of-band Gate 2 certification (audit_verdict.json)
```

### Contributor Rules
1. **Surgical Contiguous Edits (`PSL-INV-003`)**: Prefer `replace_file_content` over whole-file rewrites on source files.
2. **Product vs. Project Separation (`ADR-014`)**: Keep empirical data in `data/`, research/archives in `docs/archive/`, and scratch artifacts outside `harness/`.
3. **Hermetic Verification (`PSL-INV-001`)**: Add or update hermetic tests under `tests/` (`tempfile.TemporaryDirectory()`, zero network calls) and see [`testing-contracts.md`](official-specs/testing-contracts.md), [`empirical-baselines.md`](taxonomy/empirical-baselines.md), [`project-ledger.md`](taxonomy/project-ledger.md), [`docs/adr/README.md`](adr/README.md), and [`docs/runbooks/git-and-worktree-hygiene.md`](runbooks/git-and-worktree-hygiene.md).
