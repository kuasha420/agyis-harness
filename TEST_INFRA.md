<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# E2E Test Infra: Route C Swarm Hardening (Issue #83)

## Test Philosophy
- **Requirement-Driven & Opaque-Box**: Derive tests strictly from `ORIGINAL_REQUEST.md` and `COMPLETION_LEDGER.md`.
- **Hermetic Isolation**: Zero network access, zero daemon dependencies, state isolation using temporary directories (`PSL_HARNESS_STATE_DIR`).
- **Sub-Second Benchmark (ADR-015)**: The dedicated test suite `tests/test_compaction_advisory.py` must execute in `<1.0s`.
- **Zero-Regression Invariant**: Universal project test suite (`./agyis test` / `python3 -m harness.cli test`) must pass 100% cleanly with exit code 0.

## Feature Inventory & Test Mapping
| # | Feature | Source (Requirement) | Tier 1 (Coverage) | Tier 2 (Boundary) | Tier 3 (Cross-Feature) | Tier 4 (Scenario) |
|---|---------|----------------------|:-----------------:|:-----------------:|:---------------------:|:-----------------:|
| 1 | F1: Runner Aliases | ORIGINAL_REQUEST §R1 | test_runner_alias_compaction_advisory | alias with spaces / case variants | alias + corrupt payload | CLI + Runner pipeline |
| 2 | F2: Fail-Open Normalization | ORIGINAL_REQUEST §R1 | test_fail_open_pre_invocation_schema | empty string / non-json / binary garbage | alias + missing hook module | exception during turn |
| 3 | F3: CLI Whitelist | ORIGINAL_REQUEST §R1 | test_cli_hook_compaction_advisory | unexpected flag / unknown hook | CLI piping stdin | end-to-end CLI exec |
| 4 | F4: Ingress Key Alignment | ORIGINAL_REQUEST §R2 | test_classify_from_workspace_paths | empty array / nested path dicts | activeWorkspaces + workspacePaths together | subagent invocation |
| 5 | F5: Custodian Role Mapping | ORIGINAL_REQUEST §R2 | test_classify_custodian_role | mixed-case role strings | custodian worktree + payload role | SWE ladder pipeline |
| 6 | F6: Modern Protobuf Inspection | ORIGINAL_REQUEST §R2 | test_sqlite_modern_protobuf_columns | empty steps table / missing db | corrupt blob data / lock timeout | live conversation db |
| 7 | F7: Calibration Metadata | ORIGINAL_REQUEST §R3 | test_calibration_metadata_access | boundary values in dictionary | metadata + threshold evaluation | programmatic access |
| 8 | F8: Dynamic Runway Calculation | ORIGINAL_REQUEST §R3 | test_dynamic_remaining_turns | tokens=229k, 245k, 246k, 300k | dynamic turns + custom threshold | warning progression |
| 9 | F9: Expanded Verification | ORIGINAL_REQUEST §R4 | test_post_compaction_silence | step_type=23 barrier boundary | multi-checkpoint sequence | compaction recovery |
| 10 | F10: Adversarial Hardening | ORIGINAL_REQUEST §R5 | test_adversarial_stress | large payload / rapid token bursts | race conditions / concurrent ro read | full swarm lifecycle |

## Test Architecture
- **Test Runner**: Standard `unittest` runner (`python3 -m unittest discover -s tests -v`) and harness CLI runner (`python3 -m harness.cli test`).
- **Dedicated Suite**: `tests/test_compaction_advisory.py`.
- **Target Metrics**: 36+ passing unit tests in `<0.10s` (exceeding ADR-015 requirement of `<1.0s`).

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Expected Outcome |
|---|----------|--------------------|------------------|
| 1 | SWE Ladder Custodian Worktree | F4, F5, F8 | Role evaluates to `deep_execution`, advisory forbids `git reset --hard`, dynamic turns displayed |
| 2 | Runner Subprocess Ingress | F1, F2, F3 | `agyis hook compaction-advisory` returns `{"injectSteps": [...]}` or fails open to `{"injectSteps": []}` |
| 3 | Compaction Checkpoint Boundary | F6, F8, F9 | Post-compaction context drop resets token guard; hook operates silently (`{"injectSteps": []}`) |
| 4 | Corrupted Ingress Stream | F2, F3 | Binary noise on stdin causes graceful exit 0 with `{"injectSteps": []}` |

## Coverage Thresholds
- Tier 1: ≥5 tests per feature
- Tier 2: Boundary testing at 229,999, 230,000, 245,941, 246,000 tokens, empty schemas, and corrupt JSON
- Tier 3: Pairwise validation across CLI aliases, ingress schemas, and SQLite state
- Tier 4: Real-world workflow simulations
- All tests must pass with exit code 0 under `<1.0s`.
