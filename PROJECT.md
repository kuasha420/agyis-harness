<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Project: agyis-harness Rebrand & Autonomous Agent Runtime

## Architecture
- **Core CLI & Runtime (`harness/cli.py`, `harness/runtime/`)**: Primary executable `agyis` with backward-compatible `psl` deprecation shim (1-month warning on stderr, 3-month removal). Discreet backronym "Antigravity Immune System" in doctor and CLI metadata.
- **Config & State Hierarchy (`harness/telemetry/config.py`, `harness/utils/state.py`)**: `AGYIS_*` env vars and `~/.config/agyis`, `~/.local/share/agyis` with automatic fallback to legacy `PSL_*` env vars and `~/.config/psl`, `~/.local/share/psl`.
- **Packaging & Manifest (`pyproject.toml`, `package.json`, `plugin.json`)**: Product name `agyis-harness`, console scripts `agyis` and `psl`. Extension registered as `agyis-harness`.
- **Specialist Personas (`harness/agents/`, `harness/subagents/`)**: `psl_main` promoted to `agyis_architect` with full 17-tool capability bundle and backward-compatible alias resolution.
- **Rule Demarcation & Stack Presets (`harness/delivery/workspace.py`, `harness/skills/`)**: Tagged block `<!-- Added by AGYIS-HARNESS -->` ... `<!-- End AGYIS-HARNESS -->` with dual regex matching legacy `PSL-HARNESS` blocks. Systems stack detection (Makefile, CMakeLists.txt, meson.build, flake.nix, PKGBUILD) and explicit command dictionary extraction.
- **Harmonizer Engine (`harness/delivery/harmonize.py`, `harness/commands/harmonize.py`)**: `agyis harmonize [path] [--dry-run] [--json]` non-destructively converting legacy `<!-- Added by PSL-HARNESS -->` and `.agent/` structures to `.agents/`.
- **Licensing & Stewardship (`LICENSE`, `NOTICE`, file headers)**: Apache-2.0 with CSP-IP attribution under ICARO-42/b (Author: Arafat Zahan @kuasha420, Stewardship: Purrfect Software Limited).
- **Hermetic Testing & Invariants (`tests/`, `harness/hooks/`)**: Dual assertions for `agyis` and `psl`, 412+ tests passing 100% in <2.0s (target <1.0s) with clean-room isolation.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Primary CLI Executable `agyis` | Transition primary CLI binary and console entrypoints to `agyis` | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Backward-Compatible `psl` Shim | `psl` executable with stderr deprecation warning (1-mo warning, 3-mo removal) | M1 | ORIGINAL_REQUEST §R1 |
| 3 | XDG Path Migration & Env Fallbacks | State/config paths `~/.config/agyis` & `~/.local/share/agyis`, `AGYIS_*` with `PSL_*` fallbacks | M1 | ORIGINAL_REQUEST §R1 |
| 4 | Extension Manifest Rebrand | Register `agyis-harness` in `plugin.json` | M1 | ORIGINAL_REQUEST §R3 |
| 5 | Specialist Persona Evolution | Promote `psl_main` to `agyis_architect.md`, assert valid schemas and backward-compatible aliases | M1 | ORIGINAL_REQUEST §R3 |
| 6 | Tagged Rule Demarcation | Fencing `<!-- Added by AGYIS-HARNESS -->` with dual regex matching legacy blocks | M2 | ORIGINAL_REQUEST §R2 |
| 7 | Stack Preset Auto-Detection & Systems | Auto-detect Systems stack (Makefile, etc.) + Node/TS/Python/Rust/Go in `init` | M2 | ORIGINAL_REQUEST §R2 |
| 8 | Command Dictionary Extraction | Extract explicit command dictionaries from package.json, pyproject.toml, Makefile | M2 | ORIGINAL_REQUEST §R2 |
| 9 | `agyis init --dry-run` | Support `--dry-run` flag for previewing workspace initialization | M2 | ORIGINAL_REQUEST §R2 |
| 10 | `agyis harmonize` CLI & Runtime | Non-destructive migration of `.agent/` to `.agents/` and legacy tagged blocks with `--dry-run` | M2 | ORIGINAL_REQUEST §R2 |
| 11 | CSP-IP Attribution & Notice | Apache-2.0 with CSP-IP ICARO-42/b header attribution and updated `NOTICE` file | M3 | ORIGINAL_REQUEST §Acceptance |
| 12 | Doctor Diagnostics & Backronym | Probe `agyis` binary, preserve `psl` collision check, integrate subtle "Antigravity Immune System" | M3 | ORIGINAL_REQUEST §R3, §Acceptance |
| 13 | Hook & Remote Dual Runner Recognition | Add `agyis` to universal test runner patterns, toolchain shims, and SSH patterns | M4 | ORIGINAL_REQUEST §R4 |
| 14 | Hermetic Test Suite Dual Assertions | 100% test pass rate asserting both `agyis` and `psl` in <2.0s (target <1.0s) | M4 | ORIGINAL_REQUEST §R4 |
| 15 | Hermetic Harmonizer Test Suite | Unit & integration tests for harmonize engine and command dictionary in `tests/test_harmonize.py` | M4 | ORIGINAL_REQUEST §R4 |
| 16 | Fleet Healing Live Dry-Run | Run `agyis init --dry-run` and `agyis harmonize --dry-run` on purrmission and psl-scaffold with 0 git diff | M5 | ORIGINAL_REQUEST §R5 |
| 17 | In-Tree RFC Documentation | Ensure `docs/discussions/rebrand-agyis-epic.md` is committed and up to date | M5 | ORIGINAL_REQUEST §R5 |
| 18 | Opaque-Box E2E Test Suite | 4-tier requirement-driven E2E test suite covering R1-R5, publishing TEST_READY.md | E2E-Track | Dual Track Mandate |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Core CLI, Nomenclature, Paths & Manifest | Features 1, 2, 3, 4, 5 (R1, R3): entrypoints, `harness/cli.py`, XDG configs, `plugin.json`, `agyis_architect.md` | none | DONE |
| M2 | Rule Fencing, Stack Presets & Harmonizer | Features 6, 7, 8, 9, 10 (R2): dual tags, Systems stack, command dictionary, `harmonize` command | M1 | DONE |
| M3 | Licensing, CSP-IP Attribution & Doctor Diagnostics | Features 11, 12 (R3, Standards): NOTICE, LICENSE, headers, doctor diagnostics & backronym | M1 | DONE |
| M4 | Test Suite Dual Assertions & Hermetic Benchmarks | Features 13, 14, 15 (R4): hook patterns, test runner, dual assertions, <1.0s benchmark | M2, M3 | DONE |
| M5 | Fleet Healing Dry-Run & Epic Documentation | Features 16, 17 (R5): live dry-run checks on external repos, RFC verification, final acceptance | M4, E2E-Track | DONE |
| E2E | Requirement-Driven Opaque-Box E2E Testing | Feature 18: 4-tier E2E test harness and test suite validating R1-R5, publishing TEST_READY.md | none (parallel) | DONE |

## Interface Contracts
### CLI & Entrypoints ↔ Subcommands
- `agyis [subcommand] [args...]`: Dispatches cleanly to subcommand handlers (`cmd_doctor`, `cmd_test`, `cmd_init`, `cmd_harmonize`, etc.).
- `psl [subcommand] [args...]`: Emits 1-month deprecation notice to `sys.stderr` (`"DeprecationWarning: 'psl' is deprecated and will be removed in 3 months. Use 'agyis' instead."`), then executes identical workflow.
- Exit codes: 0 on success, non-zero on failure. Stdout reserved for clean data / `--json` output.

### Telemetry Config ↔ XDG Paths
- `get_config_dir(ws=None) -> Path`: Evaluates `AGYIS_CONFIG_DIR` -> `PSL_CONFIG_DIR` -> `~/.config/agyis` -> `~/.config/psl` -> `~/.config/agyis`.
- `get_data_dir() -> Path`: Evaluates `AGYIS_DATA_DIR` -> `PSL_DATA_DIR` -> `~/.local/share/agyis` -> `~/.local/share/psl` -> `~/.local/share/agyis`.

### Harmonizer Engine ↔ Workspace
- `harmonize_workspace(ws_path: Path, dry_run: bool = False) -> HarmonizeResult`:
  - Scans `ws_path` for `.agent/` and `AGENTS.md`.
  - Migrates `.agent/agents/` to `.agents/agents/`.
  - Migrates `.agent/workflows/*.md` to `.agents/skills/<name>/SKILL.md` (synthesizing frontmatter if missing).
  - Copies `.agent/rules/` to `.agents/rules/`.
  - Replaces `<!-- Added by PSL-HARNESS -->` blocks with `<!-- Added by AGYIS-HARNESS -->` preserving user rules.
  - Returns `HarmonizeResult` containing migrated files, status, and modified flag.

## Code Layout
- `harness/`: Distributable extension runtime (Clean, zero third-party dependencies, <1.0s benchmark)
  - `cli.py`: Primary CLI dispatcher (`prog="agyis"`, `psl` deprecation shim)
  - `commands/`: Subcommand handlers (`test.py`, `doctor.py`, `init.py`, `harmonize.py`, `skills.py`, `agents.py`, etc.)
  - `delivery/`: Workspace delivery, installer, bin launcher, harmonization engine (`workspace.py`, `harmonize.py`, `installer.py`, `bin_launcher.py`)
  - `runtime/`: Doctor diagnostics, tool checks, environment auto-healing (`doctor.py`, `tool_checks.py`, `healing.py`)
  - `hooks/`: Antigravity lifecycle hooks (`completion_fence_hook.py`, `command_safety_hook.py`, `anti_loop_hook.py`, `output_compactor_hook.py`, `anti_drift_hook.py`)
  - `agents/`: Specialist subagent personas (`agyis_architect.md`, `coordinator.md`, `planner.md`, `harness_builder.md`, etc.)
  - `subagents/`: Agent specification parsing, validation, and scaffolding (`spec.py`, `validator.py`, `scaffold.py`)
  - `telemetry/`: Configuration, database, and telemetry sync (`config.py`, `database.py`, `sync.py`)
- `tests/`: Hermetic test suite (<1.0s benchmark)
  - `test_cli.py`, `test_delivery.py`, `test_harmonize.py`, `test_psl_doctor.py`, `test_completion_fence.py`, etc.
- `docs/`: Technical specifications, ADRs, discussions (`discussions/rebrand-agyis-epic.md`)
