<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Agyis Harness E2E Testing Infrastructure Specification: Issues #41-#46

This document specifies the requirement-driven, opaque-box End-to-End (E2E) testing track for `agyis-harness` covering Issues #41 through #46, codifying the 4-tier testing methodology, test suite directory layout, runner contracts, and sign-off verification gates.

---

## 1. Executive Summary & Testing Philosophy

The primary objective of the E2E Testing Track is to validate the complete product lifecycle from the perspective of an external operator, autonomous agent swarm, or continuous integration harness for Issues #41 through #46. While unit and integration tests under `tests/` inspect individual internal modules, the E2E suite under `tests/e2e/` exercises the software **strictly as an opaque box** via public CLI binaries (`agyis` and `psl`), lifecycle hook runners (`python3 -m harness.hooks.runner`), observable filesystem states, exit codes, process standard streams, and environment contracts.

### Core Testing Invariants
1. **Opaque-Box Boundary**: Test cases invoke public CLI commands (`agyis`, `psl`) and lifecycle hook dispatchers (`run_hook`, `run_hook_cli`). No private internal classes or non-public methods are monkeypatched.
2. **Hermetic Clean-Room Isolation (ADR-015)**: Every test executes in an isolated temporary directory (`tempfile.TemporaryDirectory()`). Zero network access, zero daemon dependencies, and scrubbed XDG paths (`PSL_HARNESS_STATE_DIR`, `AGYIS_CONFIG_DIR`, `AGYIS_DATA_DIR`).
3. **Sub-Second Execution Target**: Each individual tier executes in <1.0s, with the complete 4-tier E2E suite executing in **<3.5s** total.
4. **Requirement Traceability**: Every test case traces directly to requirements across Issues #41 through #46.

---

## 2. Feature Inventory: Issues #41-#46

| Feature ID | Issue ID | Target Area | Description | Implementation Target |
|:---|:---|:---|:---|:---|
| **F1** | Issue #41 | Anti-Loop Coordination Exemption | Exempts `.agents/teamwork/`, `.agents/ledger/`, and coordination manifests (`progress.md`, `DISPATCH.md`, `BRIEFING.md`, `handoff.md`, `task.md`, `obligations.json`) across all path argument keys (`AbsolutePath`, `Path`, `TargetFile`, `file_path`, etc.) with slash normalization. | `harness/hooks/anti_loop_hook.py` |
| **F2** | Issue #42 | Stop-Fence PostToolUse Wiring | Wires `psl-stop-verification-fence` under `PostToolUse` for `run_command` in `hooks.json` so exit code 0 of test commands immediately resets `code_dirty = False`, clears `last_modified_files`, and updates `last_verified_at`. | `hooks.json`, `harness/hooks/completion_fence_hook.py` |
| **F3** | Issue #43 | Ephemeral Scratch Path Isolation | Scopes code file dirty tracking exclusively to files within the active workspace root (`cwd`), exempting ephemeral scratch paths (`.gemini/antigravity/brain/*/scratch/*`, `/tmp/*` outside workspace) from setting `code_dirty = True`. | `harness/hooks/completion_fence_hook.py` |
| **F6** | Issue #46 | Standardized Issue Templates | Establishes GitHub Issue Forms (`.github/ISSUE_TEMPLATE/bug_report.yml`, `feature_request.yml`, `config.yml`) mandating `harness_version` and capturing optional platform/toolchain metadata. | `.github/ISSUE_TEMPLATE/` |

---

## 3. 4-Tier Test Architecture

```
                    ┌────────────────────────────────────────┐
                    │      Tier 4: Real-World Scenarios      │
                    │   (5 Realistic Multi-Step Workflows)   │
                    └───────────────────▲────────────────────┘
                                        │
                    ┌───────────────────┴────────────────────┐
                    │   Tier 3: Cross-Feature Interactions   │
                    │     (8 Multi-Subsystem Combinations)   │
                    └───────────────────▲────────────────────┘
                                        │
                    ┌───────────────────┴────────────────────┐
                    │     Tier 2: Boundary & Corner Cases    │
                    │    (30 Edge, Malformed, Slash Tests)   │
                    └───────────────────▲────────────────────┘
                                        │
                    ┌───────────────────┴────────────────────┐
                    │       Tier 1: Feature Coverage         │
                    │    (30 Tests: 5 per Feature F1-F6)     │
                    └────────────────────────────────────────┘
```

### 3.1 Tier 1: Feature Coverage (`tests/e2e/test_tier1_features.py`)
Validates that each feature behaves strictly according to specification across its nominal operating range (5 tests per feature, 30 tests total):
- **Feature 1 (Issue #41: Anti-Loop Coordination Exemption)**:
  - `test_f1_01_teamwork_directory_progress_repeated_view`: 10 consecutive inspections of `.agents/teamwork/progress.md` produce 0 denials.
  - `test_f1_02_ledger_directory_obligations_repeated_view`: 10 consecutive inspections of `.agents/ledger/obligations.json` produce 0 denials.
  - `test_f1_03_coordination_basenames_dispatch_briefing_task`: Exempts `DISPATCH.md`, `BRIEFING.md`, `handoff.md`, `task.md`.
  - `test_f1_04_argument_name_invariance`: Path invariance across `AbsolutePath`, `Path`, `TargetFile`, `file_path`, `filePath`, etc.
  - `test_f1_05_production_code_rate_limited`: Confirms production code (`src/`, `harness/`) remains strictly subject to loop guard denials.
- **Feature 2 (Issue #42: Stop-Fence Wiring)**:
  - `test_f2_01_post_tool_use_test_command_exit_zero_clears_dirty`: Test command with exit 0 clears `code_dirty = False`.
  - `test_f2_02_post_tool_use_test_command_exit_nonzero_retains_dirty`: Test command with exit 1 retains `code_dirty = True`.
  - `test_f2_03_stop_event_allowed_after_successful_verification`: `evaluate_stop` returns `allow` on first attempt after verification.
  - `test_f2_04_post_tool_use_resets_modified_files_and_updates_timestamp`: Passing test resets `last_modified_files` and records timestamp.
  - `test_f2_05_post_tool_use_hooks_json_registration`: Confirms `PostToolUse` for `run_command` is wired in `hooks.json`.
- **Feature 3 (Issue #43: Scratch Path Isolation)**:
  - `test_f3_01_brain_scratch_path_does_not_dirty_state`: Edits in `.gemini/antigravity/brain/*/scratch/*` do not set dirty.
  - `test_f3_02_temp_scratch_path_outside_workspace_does_not_dirty`: Edits in `/tmp/*` outside workspace do not set dirty.
  - `test_f3_03_workspace_code_edit_sets_dirty_true`: In-workspace code edits mark dirty.
  - `test_f3_04_scratch_edit_allows_immediate_stop`: Task authoring only scratch files may terminate immediately.
  - `test_f3_05_relative_path_outside_workspace_isolated`: Relative paths resolving outside workspace root are isolated.
- **Feature 6 (Issue #46: Issue Templates)**:
  - `test_f6_01_bug_report_template_exists_and_valid_yaml`: Validates `bug_report.yml` exists and has valid structure.
  - `test_f6_02_bug_report_mandates_harness_version`: Asserts `harness_version` is marked `required: true`.
  - `test_f6_03_bug_report_optional_antigravity_platform_fields`: Checks optional `antigravity_cli_version` and `antigravity_ide_version`.
  - `test_f6_04_bug_report_optional_toolchain_and_repo_fields`: Checks `host_toolchain_versions` and `reproduction_repo`.
  - `test_f6_05_feature_request_and_config_templates_valid`: Validates `feature_request.yml` and `config.yml`.

### 3.2 Tier 2: Boundary & Corner Cases (`tests/e2e/test_tier2_boundaries.py`)
Probes edge cases, malformed payloads, and boundary conditions (5 tests per domain, 20 tests total):
- **Domain 1: Anti-Loop Boundaries**: Empty path, Windows backslashes, whitespace padding, case variations, deeply nested paths.
- **Domain 2: Stop-Fence Boundaries**: Non-test command exit 0, null exit code, negative/signal exit codes, malformed JSON, unknown tools.
- **Domain 3: Scratch Path Boundaries**: Workspace inside /tmp, brain scratch nested paths, path traversal (`../`), symlinked scratch dir, empty path.
- **Domain 6: Issue Template Boundaries**: Syntax formatting, required `body` key, non-YAML files ignored, special characters and code blocks in descriptions, validations structure integrity.

### 3.3 Tier 3: Cross-Feature Interactions (`tests/e2e/test_tier3_combinations.py`)
Validates critical cross-feature interactions and subsystem combinations (5 tests total):
- `test_c3_anti_loop_test_reset_plus_stop_fence_clearance`: Code edit counter reset + Test runner clearance.
- `test_c5_doctor_toolchain_audit_plus_template_correlation`: Doctor output keys match template fields.
- `test_c6_multi_agent_teamwork_views_plus_scratch_authoring`: Swarm teamwork views + Scratch script authoring.
- `test_c7_diverse_test_runner_patterns_recognition`: Python, Cargo, npm, pnpm, Make, shell runner clearance.
- `test_c8_anti_deadlock_valve_trips_on_attempt_three`: Anti-deadlock valve tripping on attempt 3.

### 3.4 Tier 4: Real-World Scenarios (`tests/e2e/test_tier4_scenarios.py`)
Executes end-to-end user journeys mirroring production workflows (3 tests total):
- `test_s1_multi_agent_swarm_coordination_journey`: Multi-agent swarm reading dispatch, progress, and obligations.
- `test_s2_diagnostic_scratch_investigation_journey`: Diagnostic triage authoring scratch scripts without dirtying repo.
- `test_s5_bug_report_submission_with_doctor_integration_journey`: Automated bug report creation with doctor telemetry.

---

## 4. Test Suite Directory Layout

```
tests/e2e/
├── __init__.py                     # Package marker
├── harness_base.py                 # OpaqueBoxTestCase sandboxing, CLI & hook helpers
├── test_tier1_features.py          # Tier 1: Feature Coverage (30 tests)
├── test_tier2_boundaries.py        # Tier 2: Boundary & Corner Cases (30 tests)
├── test_tier3_combinations.py      # Tier 3: Cross-Feature Combinations (8 tests)
└── test_tier4_scenarios.py         # Tier 4: Real-World Application Scenarios (5 tests)
```

---

## 5. Runner Invocations & Benchmark Budgets

### Standard Test Runner Invocations
```bash
# 🧪 Run Complete 4-Tier E2E Test Suite
python3 -m unittest discover -s tests/e2e -v

# 🧪 Run Specific Tiers
python3 -m unittest tests/e2e/test_tier1_features.py -v
python3 -m unittest tests/e2e/test_tier2_boundaries.py -v
python3 -m unittest tests/e2e/test_tier3_combinations.py -v
python3 -m unittest tests/e2e/test_tier4_scenarios.py -v

# 🧪 Run via Project CLI Test Runner
python3 -m harness.cli test -s tests/e2e -v
```

### Benchmark Budgets
| Test Suite Tier | Target Test Count | Maximum Runtime Budget | Hermeticity Requirement |
|:---|:---|:---|:---|
| **Tier 1: Features** | 20 tests | < 1.0s | 100% In-Memory / Clean-room Tempdir |
| **Tier 2: Boundaries** | 20 tests | < 1.0s | 100% In-Memory / Clean-room Tempdir |
| **Tier 3: Combinations** | 5 tests | < 0.8s | 100% In-Memory / Clean-room Tempdir |
| **Tier 4: Scenarios** | 3 tests | < 0.8s | 100% In-Memory / Clean-room Tempdir |
| **Complete E2E Suite** | **48 tests** | **< 2.0s** | **Zero Network / External Deps** |

---

## 6. Requirement Traceability Matrix

| Requirement / Issue | Target Features | Test Class | Key Verifications |
|:---|:---|:---|:---|
| **Issue #41** | Anti-Loop Coordination Exemption | `TestTier1Features.test_f1_*`<br>`TestTier2Boundaries.test_b1_*`<br>`TestTier3Combinations.test_c2,c3,c6`<br>`TestTier4Scenarios.test_s1` | Repeated views of `.agents/teamwork/` and `.agents/ledger/`, manifest basenames, argument invariance, Windows backslashes, whitespace trimming |
| **Issue #42** | Stop-Fence PostToolUse Clearance | `TestTier1Features.test_f2_*`<br>`TestTier2Boundaries.test_b2_*`<br>`TestTier3Combinations.test_c3,c4,c7,c8`<br>`TestTier4Scenarios.test_s3` | PostToolUse exit 0 clearance, exit 1 retention, hooks.json wiring, universal test runner patterns, anti-deadlock valve |
| **Issue #43** | Ephemeral Scratch Path Isolation | `TestTier1Features.test_f3_*`<br>`TestTier2Boundaries.test_b3_*`<br>`TestTier3Combinations.test_c1,c4,c6`<br>`TestTier4Scenarios.test_s2` | Brain scratch paths, /tmp outside workspace, workspace root inside /tmp, relative traversal scrubbing, immediate stop |
| **Issue #46** | Standardized Issue Templates | `TestTier1Features.test_f6_*`<br>`TestTier2Boundaries.test_b6_*`<br>`TestTier3Combinations.test_c5`<br>`TestTier4Scenarios.test_s5` | YAML form schema validity, mandatory `harness_version`, optional platform/toolchain fields, validations block integrity |

---

## 7. Publication Protocol for `TEST_READY.md`

When the E2E test suite implementation is complete and verified:
1. All 4 tiers must be implemented under `tests/e2e/`.
2. Execution of `python3 -m unittest discover -s tests/e2e -v` must report:
   - Exactly 48 tests registered across all 4 tiers (20 + 20 + 5 + 3).
   - 0 failures, 0 errors (with graceful milestone skips allowed where components are pending concurrent worker completion).
   - Execution time strictly under 2.0s.
3. The file `TEST_READY.md` must be published at the repository root detailing:
   - **Status**: `READY`
   - **Total Test Count**: Exact count across all 4 tiers (48 tests).
   - **Benchmark Metrics**: Exact execution duration.
   - **Runner Commands**: Explicit CLI palettes.
   - **Invariants Checklist**: Hermetic cleanroom, zero network, opaque-box boundary.
