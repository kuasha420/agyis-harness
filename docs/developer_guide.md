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

Every design decision in `agyis-harness` enforces a strict architectural separation between **The Product** (distributed globally to developer workstations) and **The Project** (the empirical telemetry laboratory and development workspace):

```text
agyis-harness/
├── pyproject.toml            # Zero-dependency standard-library Python package (dependencies = [])
├── plugin.json               # Google Antigravity plugin manifest ("agyis-harness", v1.0.0-rc10)
├── matrix.json               # 3-Tier Runtime Dependency Matrix (Languages, SWE CLI, Mesh)
├── hooks.json                # Declarative lifecycle hook registrations (7 hooks -> harness/hooks/)
│
├── harness/                  # [THE PRODUCT] Distributable core package
│   ├── __init__.py           # Package version (__version__ = "1.0.0-rc10")
│   ├── cli.py                # Unified 27-command `agyis` CLI dispatcher (`psl` legacy alias)
│   ├── discovery.py          # Global/workspace resource discovery & root path resolution
│   ├── agents/               # 8 canonical `agyis_*` specialist personas + alias bridge
│   ├── cleanroom/            # Specification, obligation ledger, and REA reconstruction verifiers
│   ├── commands/             # Modular command handlers (25 handler modules + __init__.py backing 27 subcommands)
│   ├── delivery/             # Installer, workspace harmonizer, onboarder, git topology, checkpoints
│   ├── doctor/               # Modular diagnostics & health check runners
│   ├── gui/                  # Antigravity Electron CDP WebSocket unlockers & HUD (`assets/hud.js` via importlib.resources)
│   ├── harmonize/            # Legacy `.agent/` -> `.agents/` harmonization engine
│   ├── hooks/                # 7 deterministic lifecycle guards + `hooks.json` (fail-safe CLI & JSON runner)
│   ├── mutation/             # Atomic file mutation & backup/patch helpers
│   ├── re/                   # Cleanroom reverse-engineering & REA integration modules
│   ├── remote/               # ControlMaster SSH multiplexing & compact triage (<2KB)
│   ├── rules/                # Curated agent governance (`GLOBAL_AGENTS.md` vs `AGENTS.md`)
│   ├── runtime/              # Toolchain diagnostics, zero-sudo healing & hygiene checks
│   ├── skills/               # 30 modular operational & test-runner skills (`.agents/skills/` symlinks)
│   ├── subagents/            # Routing (`routing.py`), liveness, truth, succession, spec & scaffolding
│   ├── telemetry/            # Session harvester, hub sync client & systemd user service daemon
│   └── utils/                # Shared helpers including trajectory/context metadata (`context.py`)
│
├── pipeline/                 # [THE PROJECT] Telemetry extraction & empirical classification lab
├── data/                     # [THE PROJECT] Local empirical SQLite telemetry store (`telemetry.db`)
├── docs/                     # [THE PROJECT] ADRs, Official Specs, Runbooks, Taxonomy & Guides
└── tests/                    # [THE PROJECT] 1,981 hermetic unit, integration, contract & E2E tests
```

### Key Non-Negotiable Architecture Rules
1. **Zero Mandatory External Dependencies**: `harness/` uses **strictly Python 3.12+ standard library** (`sqlite3`, `json`, `urllib`, `pathlib`, `subprocess`, `ast`, `importlib.resources`). Never import `pytest`, `requests`, `pydantic`, or `pipeline/` inside `harness/` (enforced by `agyis audit aff` / PSL-INV-011).
2. **Externalized Foreign Assets (PSL-INV-011)**: Never embed large JavaScript, CSS, HTML, or SQL monoliths as inline strings inside Python modules. Place frontend/HUD scripts in `harness/gui/assets/` and load them via `importlib.resources` (`harness.gui.assets`).
3. **Hermetic State Isolation (`PSL_HARNESS_STATE_DIR`)**: All persistent runtime files (hook loop counters, completion fence dirty state, compaction advisory markers) honor `PSL_HARNESS_STATE_DIR` (defaulting to `/tmp/agyis_harness_state/`). Unit tests must always inject isolated temporary directories via `tempfile.TemporaryDirectory()`.

---

## 2. The Unified 27-Command CLI Architecture (`harness/cli.py`)

All developer, operator, and agent functionality lives behind `agyis` (`python3 -m harness.cli`, with backward-compatible `psl` alias):

| Domain | Commands (`27` + aliases) | Primary Backing Modules |
| :--- | :--- | :--- |
| **Diagnostics & Testing** | `doctor`, `test`, `status` | `harness/commands/{doctor,test,status}.py`, `harness/runtime/` |
| **Lifecycle Hooks** | `hook` | `harness/commands/hook.py`, `harness/hooks/runner.py` |
| **Orchestration & Compaction** | `cockpit`, `router` (`ladder`), `checkpoint`, `subagents` | `harness/commands/{cockpit,checkpoint,subagents}.py`, `harness/subagents/routing.py`, `harness/delivery/compaction_checkpoint.py` |
| **Workspace Hygiene & Onboarding** | `init`, `harmonize`, `onboard`, `clean`, `ext` | `harness/commands/{init,harmonize,onboard,clean,ext}.py`, `harness/delivery/` |
| **Governance & Discovery** | `rules`, `skills`, `agents` | `harness/commands/{rules,skills,agents}.py`, `harness/subagents/` |
| **Telemetry & AFF Audits** | `audit`, `sync`, `auth` | `harness/commands/{audit,sync,auth}.py`, `harness/telemetry/` |
| **Cleanroom & Reverse Eng.** | `verify`, `re` | `harness/commands/{verify,re}.py`, `harness/cleanroom/` |
| **Delivery, GUI & Releases** | `install`, `uninstall`, `gui`, `release-notes`, `changelog` (`changelogs`), `remote` | `harness/commands/{install,gui,release_notes,changelog,remote}.py`, `harness/gui/`, `harness/remote/` |

Authoritative CLI flags and help verification checks live in [cli-palette.md](official-specs/cli-palette.md).

---

## 3. The 7 Deterministic Lifecycle Hooks (`harness/hooks/`)

All lifecycle guards are declared in [`harness/hooks/hooks.json`](../harness/hooks/hooks.json) and executed through `python3 -m harness.hooks.runner <hook>` or `agyis hook <name>`. Every hook enforces strict fail-open invariants for platform resilience while enforcing deterministic denials when agent invariants are breached.

| # | Hook Registration ID | Event | Implementation | Responsibility |
| :- | :--- | :--- | :--- | :--- |
| 1 | `psl-command-safety-guard` | `PreToolUse` (`run_command\|manage_task\|manage_subagents`) | [`command_safety_hook.py`](../harness/hooks/command_safety_hook.py) | Prepends certified CPython 3.12 (`uv`), sets `PAGER=cat` for `git`/`gh`, normalizes benign `grep`/`diff` exit 1 (`\|\| [ $? -eq 1 ]`), promotes fragile multiline Python scripts. |
| 2 | `psl-anti-loop-guard` | `PreToolUse` (`view_file\|grep_search\|run_command\|manage_task`) | [`anti_loop_hook.py`](../harness/hooks/anti_loop_hook.py) | Breaks 3+ identical consecutive calls, enforces Strict Reactive Wait (blocks `manage_task(status)` polling and background log tailing), bounds spec edit loops. |
| 3 | `psl-output-compactor` | `PostToolUse` (`run_command\|view_file`) | [`output_compactor_hook.py`](../harness/hooks/output_compactor_hook.py) | Caps tool stdout/stderr above 2KB while retaining head 500 bytes, tail 1,000 bytes, exit codes, and error signatures (200KB pre-slice guard). |
| 4 | `psl-stop-verification-fence` | `PreToolUse` / `PostToolUse` / `Stop` | [`completion_fence_hook.py`](../harness/hooks/completion_fence_hook.py) | Tracks decoupled `code_dirty` vs `spec_dirty` state; blocks premature Stop until `agyis test` or `agyis verify --spec` clears active dirty state (ADR-022 / ADR-028). |
| 5 | `psl-anti-drift-guard` | `PreToolUse` | [`anti_drift_hook.py`](../harness/hooks/anti_drift_hook.py) | Enforces Native Plan-Mode Lock (ADR-031A), Auditor write-block (`check_auditor_write_block`), and domain validators ([`drift_validators.py`](../harness/hooks/drift_validators.py)). |
| 6 | `psl-token-proximity-guard` | `PreToolUse` | [`token_proximity_guard.py`](../harness/hooks/token_proximity_guard.py) | Decodes active conversation SQLite protobuf metrics in read-only URI mode and emits ANSI context horizon warnings. |
| 7 | `psl-compaction-advisory` | `PreInvocation` | [`pre_invocation_hook.py`](../harness/hooks/pre_invocation_hook.py) | Evaluates token runway before model prompt dispatch, enforces the 50-step executioner horizon, serializes compaction checkpoints, and injects de-spammed role advisories (ADR-033). |

See [lifecycle-hooks.md](official-specs/lifecycle-hooks.md) for JSON payload schemas and event contracts.

---

## 4. Specialist Agent Personas, Cockpit Director & Subagent Router

### Canonical Agent Catalog (`harness/agents/`)
`harness/agents/__init__.py` defines **8 canonical `agyis_*` personas** alongside `resolve_agent_name()` for transparent backwards compatibility with legacy monikers:

| Canonical Persona | Legacy Aliases Resolved | Primary Responsibility |
| :--- | :--- | :--- |
| **`agyis_architect`** | `architect`, `lead`, `main`, `psl_main`, `deep_hybrid` | System design, architecture specification, root cockpit coordination |
| **`agyis_coordinator`** | `coordinator`, `orchestrator`, `swarm_lead` | Multi-phase task decomposition and subagent routing |
| **`agyis_planner`** | `planner`, `designer`, `researcher` | Artifact-first planning (`implementation_plan.md`) |
| **`agyis_investigator`** | `investigator`, `detective`, `forensic`, `rca`, `root_cause_analyst` | Root cause analysis, forensic telemetry & binary triage |
| **`agyis_builder`** | `harness_builder`, `builder`, `executioner`, `worker`, `implementer` | Targeted implementation within declared plan boundaries |
| **`agyis_reviewer`** | `harness_reviewer`, `reviewer`, `hammer`, `inspector` | Adversarial diff inspection and invariant auditing |
| **`agyis_custodian`** | `harness_custodian`, `custodian`, `git_custodian`, `commit_gate` | Stage 4 DRY sweep, commit gate, and worktree/branch hygiene |
| **`agyis_auditor`** | `harness_auditor`, `auditor`, `qa`, `qa_verifier`, `verifier` | Independent read/execute-only QA verification (`check_auditor_write_block`) |

### Cockpit Director & Routing Workflows (`A`–`L`)
- **Cockpit Flight Director** ([cockpit-director.md](official-specs/cockpit-director.md)): Root sessions operate in Air Traffic Control posture (PSL-INV-008) via `agyis cockpit status`, `agyis cockpit route <A-L|alias>`, and `agyis cockpit verify`.
- **Dynamic Subagent Router**: `agyis router` (alias `agyis ladder`) and `harness/subagents/routing.py` dispatch structured transition payloads across the 12 canonical workflows (`A` RCA through `L` Cleanup) and 4 execution modes (Ladder, Fan-Out, Teamwork, Boost).
- **Zero-Kill Compaction Succession**: `agyis checkpoint [status|generate|create|verify|prune]` preserves micro-state into `.agents/artifacts/compaction_checkpoint_latest.md` and `cockpit_checkpoint.md` before context boundaries trigger (ADR-031A / ADR-033).

---

## 5. Electron GUI DevTools & Trajectory Debug HUD (ADR-014, PSL-INV-010)

`agyis gui` ([`harness/commands/gui.py`](../harness/commands/gui.py) + `harness/gui/`) connects over Antigravity's local Chrome DevTools Protocol (CDP) WebSocket (`DevToolsActivePort`) to unlock the Trajectory Debug View (`--devtools`, `--no-popup`, `--toggle`):
- Browser scripts and styles live in `harness/gui/assets/` (never raw Python monolith strings).
- In-situ HUD injections track active SPA routes (`/c/:id`) dynamically and tear down stale singleton DOM elements and styles before re-mounting (PSL-INV-010).

---

## 6. Cleanroom Reverse Engineering & Extensible Workspace CLI (ADR-028, ADR-034)

- **Cleanroom Verification (`agyis verify`)**: Validates declarative specifications in `docs/specs/**` (`--spec`), evaluates typed obligation ledgers against immutable evidence records, and checks scaffolded reconstruction completeness (`--scaffold`, PSL-INV-007).
- **Dirtyroom Acceleration (`agyis re`)**: Keeps `.dirtyroom/` hermetically isolated while patching `rea-agents` launchers (`patch-rea`) for `<2s` `-noanalysis -readOnly` queries against pre-analyzed Ghidra projects on `>10MB` binaries (`pre-analyze`, `find`, `decompile`, `pcap`, `disasm`, `xrefs`, PSL-INV-009).
- **Extensible Workspace CLI (`agyis ext`)**: Discovers workspace-local commands in `.agents/commands/` and `.agents/commands.json` (`list`, `run`, `init`), running them inside Agyis's hermetic CPython environment (ADR-034).

---

## 7. Verification Standards, AFF Gate & Contribution Workflow

### Running Verification Locally
```bash
# 1. Full hermetic test suite (1,981 tests in ~65s; sub-second unit/contract modules)
./agyis test
python3 -m harness.cli test

# Diff-aware / targeted execution (ADR-015 / Epic #51)
agyis test --diff            # Modified suites vs HEAD
agyis test --affected        # Impacted modules from dependency graph
agyis test --pkg tests/test_cli.py

# 2. Architectural Fitness Functions & Anti-Synthetic Test Hygiene
agyis audit aff              # Layer boundaries, DAG acyclicity, externalized assets, bounded caches
agyis doctor --anti-synthetic # Detect tautological / fake tests

# 3. Cleanroom Specifications & Workstation Readiness
agyis verify --spec
agyis verify
agyis doctor

# 4. Pre-Release Dual-Auditor Certification (Gate 2)
agyis audit certify
agyis audit verdict
```

### Contributor Rules
1. **Use `replace_file_content`** for surgical contiguous edits (PSL-INV-003). Do not perform whole-file rewrites on existing source modules.
2. **Preserve Rule Parity**: `.agents/rules/AGENTS.md` and `harness/rules/AGENTS.md` define local project command dictionaries (`agyis rules --lint` validates parity and detects duplicates).
3. **Never Pollute Product `harness/` with Project Data**: Scratchpads belong in `.agents/` or temp dirs; empirical DBs belong in `data/`.
4. **Never Ship Code Without Passing Verification**: Update or add hermetic tests under `tests/`, keep tests free of network dependencies and unbounded sleeps, and execute `python3 -m harness.cli test` and `python3 -m harness.cli audit aff` before handoff.
