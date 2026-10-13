<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Agyis Harness E2E Testing Infrastructure Specification (Feature 18)

This document specifies the requirement-driven, opaque-box End-to-End (E2E) testing track for `agyis-harness`, codifying the 4-tier testing methodology, test suite directory layout, runner contracts, and sign-off verification gates.

---

## 1. Executive Summary & Testing Philosophy

The primary objective of the E2E Testing Track is to validate the complete product lifecycle from the perspective of an external operator or autonomous agent. While unit and integration tests under `tests/` inspect individual internal modules, the E2E suite under `tests/e2e/` exercises the software **strictly as a black box** via public CLI binaries (`agyis` and `psl`), testing observable filesystem states, exit codes, process standard streams, and environment contracts.

### Core Testing Invariants
1. **Opaque-Box Boundary**: Test cases invoke only public CLI commands (`agyis`, `psl`, `python3 -m harness.cli`). No private internal classes or non-public methods are imported or monkeypatched.
2. **Hermetic Clean-Room Isolation (ADR-015)**: Every test executes in an isolated temporary directory (`tempfile.TemporaryDirectory()`). Zero network access, zero daemon dependencies, and scrubbed XDG paths (`PSL_HARNESS_STATE_DIR`, `AGYIS_CONFIG_DIR`, `AGYIS_DATA_DIR`).
3. **Sub-Second Execution Target**: Each individual tier executes in <1.5s, with the complete 4-tier E2E suite executing in **<4.5s** total.
4. **Requirement Traceability**: Every test case traces directly to requirements R1–R5 from `ORIGINAL_REQUEST.md` and Features 1–17 from `PROJECT.md`.

---

## 2. 4-Tier Test Suite Architecture

```
                    ┌────────────────────────────────────────┐
                    │      Tier 4: Real-World Scenarios      │
                    │   (5 Realistic Multi-Step Workflows)   │
                    └───────────────────▲────────────────────┘
                                        │
                    ┌───────────────────┴────────────────────┐
                    │   Tier 3: Cross-Feature Interactions   │
                    │    (Pairwise Feature Integrations)     │
                    └───────────────────▲────────────────────┘
                                        │
                    ┌───────────────────┴────────────────────┐
                    │     Tier 2: Boundary & Corner Cases    │
                    │ (Malformed, Read-Only, Edge Manifests) │
                    └───────────────────▲────────────────────┘
                                        │
                    ┌───────────────────┴────────────────────┐
                    │       Tier 1: Feature Coverage         │
                    │      (Features 1-17 across R1-R5)      │
                    └────────────────────────────────────────┘
```

### 2.1 Tier 1: Feature Coverage (`tests/e2e/test_tier1_features.py`)
Validates that each individual feature behaves strictly according to specification across its nominal operating range (minimum 5 test cases per requirement area):

- **R1: Core CLI, Nomenclature & Deprecation (Features 1, 2, 3)**:
  - `agyis --help`, `agyis --version`, exit code 0.
  - `psl --help`, `psl --version` emitting 1-month warning / 3-month removal lifecycle notice on `stderr`.
  - Subcommand execution parity between `agyis` and `psl`.
  - Config resolution: `AGYIS_CONFIG_DIR` takes precedence over `PSL_CONFIG_DIR`.
  - State resolution: `AGYIS_DATA_DIR` takes precedence over `PSL_DATA_DIR`.
- **R2: Tagged Rule Demarcation & Harmonizer (Features 6, 7, 8, 9, 10)**:
  - Tagged rule injection: `<!-- Added by AGYIS-HARNESS -->` ... `<!-- End AGYIS-HARNESS -->`.
  - Stack preset auto-detection: TypeScript/Node (`package.json`), Python (`pyproject.toml`), Rust (`Cargo.toml`), Go (`go.mod`), Systems (`Makefile`, `CMakeLists.txt`, `meson.build`, `flake.nix`, `PKGBUILD`).
  - Command dictionary extraction into Section 1 of `AGENTS.md`.
  - `agyis init --dry-run` and `agyis init` live workspace scaffolding.
  - `agyis harmonize [path] [--dry-run] [--json]` migration of `.agent/` to `.agents/`.
- **R3: Extension Manifest & Personas (Features 4, 5, 11, 12)**:
  - `plugin.json` extension registration and schema validity.
  - Specialist persona promotion (`agyis_architect.md`) with 17-tool capability bundle.
  - `agyis doctor` operational diagnostic pass (0 errors).
  - Discreet backronym "Antigravity Immune System" in diagnostics and metadata.
- **R4: Verification & Runner Recognition (Features 13, 14, 15)**:
  - `agyis test` and `psl test` test runner execution and completion fence signaling.
  - Sub-second benchmark verification across test suites.
  - Dual runner pattern recognition in lifecycle hooks.
- **R5: Fleet Healing Dry-Run & RFC Docs (Features 16, 17)**:
  - Non-destructive dry-run against sample fixtures with 0 filesystem modifications.
  - Presence and validity of in-tree RFC document `docs/discussions/rebrand-agyis-epic.md`.

### 2.2 Tier 2: Boundary & Corner Cases (`tests/e2e/test_tier2_boundaries.py`)
Probes edge cases, invalid inputs, and boundary conditions (minimum 5 test cases per domain):

- **Boundary Domain A: Workspaces & Permissions**:
  - Non-existent target directory handling (`agyis harmonize /nonexistent` -> exit code 1, clean error).
  - Empty workspace directory (clean creation of `AGENTS.md` and `.agents/`).
  - Read-only `AGENTS.md` (`chmod 0444`) under `--dry-run` succeeding without `PermissionError`.
- **Boundary Domain B: Corrupted Manifests**:
  - Truncated `package.json` (`{"name": "broken`).
  - Invalid TOML syntax in `pyproject.toml`.
  - Binary garbage in `Makefile` (`\x00\xff\xfe`).
  - Graceful fallback to default/generic toolchain commands without crashing.
- **Boundary Domain C: Rule Fencing Robustness**:
  - Empty fences (`<!-- Added by PSL-HARNESS -->\n<!-- End PSL-HARNESS -->`).
  - Mismatched delimiters (`<!-- Added by PSL-HARNESS -->` paired with `<!-- End AGYIS-HARNESS -->`).
  - Unclosed opening fence (treated safely as user rules, clean block appended).
  - User rules containing regex backreferences (`\g<1>`, `\1`, `$1`) and Unicode/emojis.
- **Boundary Domain D: Filesystem Structures**:
  - Circular symlinks in `.agent/agents/` (skipped via `is_symlink()` guard).
  - Deeply nested rule directories (`.agent/rules/a/b/c/d/e.md` preserved byte-for-byte).
  - Workflow files with no text body, or existing frontmatter missing descriptions.
- **Boundary Domain E: CLI Argument Combinations**:
  - Combining `--dry-run` and `--json` (`agyis harmonize --dry-run --json`).
  - Unknown flags returning exit code 2 and usage instructions.

### 2.3 Tier 3: Cross-Feature Combinations (`tests/e2e/test_tier3_combinations.py`)
Tests pairwise interactions between distinct harness subsystems:

- **Interaction 1: CLI (`psl`) + Harmonizer + JSON Output**:
  - `psl harmonize --json` writes deprecation warning strictly to `stderr`, while `stdout` remains 100% pure, parseable JSON without corrupting pipeline consumers.
- **Interaction 2: XDG Path Precedence + Init Scaffolding**:
  - Setting both `AGYIS_CONFIG_DIR` and legacy `PSL_CONFIG_DIR`; asserting `agyis init` writes state strictly to `AGYIS_CONFIG_DIR`.
- **Interaction 3: Polyglot Workspace + Precedence + Rule Injection**:
  - Workspace containing both `package.json` and `Makefile`; verifying TypeScript stack takes precedence, command dictionary formats both npm and make commands, and Section 1 of `AGENTS.md` receives the unified toolchain.
- **Interaction 4: Harmonize Migration + Doctor Health Check**:
  - Migrating a legacy `.agent/` workspace via `agyis harmonize`, followed by `agyis doctor` against the harmonized workspace, verifying 0 diagnostic warnings.
- **Interaction 5: Hook Runner + Dual Test Invocations**:
  - Executing `agyis test` and `psl test` to verify `completion_fence_hook` records successful verification state for both binary names.

### 2.4 Tier 4: Real-World Application Scenarios (`tests/e2e/test_tier4_scenarios.py`)
Executes 5 end-to-end user journeys mirroring production workflows:

- **Scenario 1: Legacy Workspace Modernization Journey**:
  - An operator migrates a legacy Antigravity 1.0 repository containing custom user rules, `.agent/agents/`, `.agent/workflows/`, and `.agent/rules/`.
  - Workflow: Operator runs `agyis harmonize --dry-run --json` -> verifies planned diff -> runs `agyis harmonize` -> verifies `.agents/` structure -> verifies synthesized YAML frontmatter -> verifies user rules intact.
- **Scenario 2: Brownfield Polyglot Ingestion Journey**:
  - Ingestion of an enterprise monorepo containing Node, Python, and Makefile components.
  - Workflow: Operator runs `agyis init --dry-run` -> inspects detected stack and extracted commands -> runs `agyis init` -> asserts `.agents/` created and command dictionary placed in Section 1 -> runs second `agyis init` asserting idempotence.
- **Scenario 3: Legacy Automation Script Compatibility Journey**:
  - Legacy CI/CD pipeline executing shell scripts that call `psl harmonize`, `psl doctor`, and `psl test`.
  - Workflow: Scripts execute unchanged; exit codes are 0; `stderr` logs deprecation notice; `stdout` data feeds downstream parsers cleanly.
- **Scenario 4: Fleet CI Dry-Run Audit Journey**:
  - An automated CI compliance job scans an array of workspaces using `agyis harmonize --dry-run --json`.
  - Workflow: Job asserts exit code 0, parses JSON summaries, and verifies git porcelain status remains strictly clean (0 git diff).
- **Scenario 5: Greenfield Workspace Scaffolding Journey**:
  - Creating a brand new repository from scratch.
  - Workflow: Operator runs `agyis init` -> verifies initial `AGENTS.md` with default rules -> inspects subagents (`agyis agents`) -> validates `agyis_architect` capability bundle.

---

## 3. Test Suite Directory Layout

```
tests/e2e/
├── __init__.py                     # Package marker
├── harness_base.py                 # OpaqueBoxTestCase sandboxing & CLI helpers
├── test_tier1_features.py          # Tier 1: Feature Coverage (R1–R5, Features 1–17)
├── test_tier2_boundaries.py        # Tier 2: Boundary & Corner Cases
├── test_tier3_combinations.py      # Tier 3: Cross-Feature Combinations
└── test_tier4_scenarios.py         # Tier 4: Real-World End-to-End User Journeys
```

---

## 4. Test Runner Invocations & Benchmark Budgets

### Standard Test Runner Invocations
```bash
# 🧪 Run full E2E test suite (all 4 tiers)
python3 -m unittest discover -s tests/e2e -v

# 🧪 Run specific tiers
python3 -m unittest tests/e2e/test_tier1_features.py -v
python3 -m unittest tests/e2e/test_tier2_boundaries.py -v
python3 -m unittest tests/e2e/test_tier3_combinations.py -v
python3 -m unittest tests/e2e/test_tier4_scenarios.py -v

# 🧪 Run via project CLI
python3 -m harness.cli test -s tests/e2e -v
```

### Proposed CLI Runner Extension
Extend `harness/cli.py` and `harness/commands/test.py` to support `--e2e`:
```bash
agyis test --e2e                    # Executes tests/e2e suite
psl test --e2e                      # Executes tests/e2e suite with deprecation notice
```

### Benchmark Budgets
| Test Suite Tier | Target Test Count | Maximum Runtime Budget | Hermeticity Requirement |
|-----------------|-------------------|------------------------|-------------------------|
| Tier 1: Features | 20+ tests | < 1.0s | 100% In-Memory / Tempdir |
| Tier 2: Boundaries | 15+ tests | < 1.0s | 100% In-Memory / Tempdir |
| Tier 3: Combinations | 8+ tests | < 1.0s | 100% In-Memory / Tempdir |
| Tier 4: Scenarios | 5+ tests | < 1.5s | 100% In-Memory / Tempdir |
| **Complete E2E Suite** | **48+ tests** | **< 4.5s** | **Zero Network / External Deps** |

---

## 5. Requirement Traceability Matrix

| Requirement | Features | E2E Test Suite Class | Key Verifications |
|-------------|----------|----------------------|-------------------|
| **R1** | 1, 2, 3 | `TestTier1Features.test_r1_*` | Primary `agyis`, deprecated `psl` warning on stderr, XDG config/data path precedence, env fallbacks |
| **R2** | 6, 7, 8, 9, 10 | `TestTier1Features.test_r2_*` | `AGYIS-HARNESS` tagged fences, stack auto-detection, command dictionary, `--dry-run`, `harmonize` |
| **R3** | 4, 5, 11, 12 | `TestTier1Features.test_r3_*` | `plugin.json` manifest, `agyis_architect` persona, doctor diagnostics, discreet backronym |
| **R4** | 13, 14, 15 | `TestTier1Features.test_r4_*` | Dual runner patterns in hooks, completion fence verification, hermetic test pass in <2.0s |
| **R5** | 16, 17 | `TestTier1Features.test_r5_*` | Live/fixture dry-run zero git diff, `docs/discussions/rebrand-agyis-epic.md` validity |
| **Boundaries** | All | `TestTier2Boundaries.test_boundary_*` | Read-only permissions, truncated manifests, corrupted fences, symlinks, missing workspaces |
| **Interactions** | All | `TestTier3Combinations.test_cross_*` | Pairwise integration: CLI+XDG, PSL+Harmonize+JSON, Multi-stack, Harmonize+Doctor |
| **Scenarios** | All | `TestTier4Scenarios.test_journey_*` | 5 full realistic workflows: Modernization, Polyglot, Operator compatibility, Fleet audit, Scaffolding |

---

## 6. Publication Protocol for `TEST_READY.md`

When the E2E test suite implementation is complete and verified:
1. All 4 tiers must be implemented under `tests/e2e/`.
2. Execution of `python3 -m unittest discover -s tests/e2e -v` must report:
   - 100% passing tests (0 failures, 0 errors).
   - Execution time strictly under 4.5s.
3. The file `TEST_READY.md` must be published at the repository root detailing:
   - **Status**: `READY`
   - **Total Test Count**: Exact count across all 4 tiers.
   - **Benchmark Metrics**: Exact execution duration.
   - **Runner Commands**: Explicit CLI palettes.
   - **Operator Sign-Off**: Verification signature.
