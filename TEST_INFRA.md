<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Agyis Harness E2E Testing Infrastructure Specification: 360-Degree Telemetry Audit Deliverables

This document specifies the requirement-driven, opaque-box End-to-End (E2E) and cross-validation testing methodology for the **360-Degree Telemetry Audit & Emergent Pattern Mining** project (`psl-agy-harness`). It codifies the 4-tier testing architecture, test directory layout, runner contracts, and verification gates governing all audit deliverables.

---

## 1. Executive Summary & Testing Philosophy

The primary objective of the Telemetry Audit Verification Track is to provide comprehensive, independent, and automated quality assurance across all audit deliverables—spanning the 568 MB telemetry database (`data/telemetry.db`), analytical forensics modules (`pipeline/`), intermediate JSON caches (`data/*.json`), CLI dispatchers (`./agyis audit`), and the definitive evidence-grounded synthesis report (`docs/reports/360_telemetry_audit_2026_10.md`).

### Core Testing Invariants

1. **Opaque-Box Boundary**:
   - Verification tests validate system deliverables through observable states: SQLite schemas and row queries, public module interfaces (`pipeline.*`), intermediate JSON caches, CLI dispatchers, and final Markdown report deliverables.
   - Tests do not alter production code or monkeypatch internal functions.
2. **Hermetic Clean-Room Isolation (ADR-015 & PSL Test Skill)**:
   - Pipeline execution tests run in isolated temporary environments (`tempfile.TemporaryDirectory()`).
   - Read-only operations against `data/telemetry.db` use strictly read-only connections and parameterized queries.
   - Zero network dependencies, zero daemon requirements, and zero disk leaks.
3. **Sub-Second Benchmark Invariant (ADR-015)**:
   - The test suite (`tests/test_audit_report.py`) executes in strictly **<1.0s** total (measured at ~0.05s–0.15s).
   - Eliminates unnecessary filesystem sweeps, slow loops, or unneeded sleep delays.
4. **Progressive Testability**:
   - Tests accommodate work-in-progress deliverables gracefully: report structural validation asserts on the live deliverable when present on disk, while validating core contracts against verified templates and fixtures if executed prior to final report authoring.
5. **Mathematical & Forensic Grounding**:
   - Every quantitative metric cited in the audit deliverables is cross-checked against actual SQLite query results (`sessions`, `steps`, `tool_calls`, `user_interventions`).
   - Every cited session is verified for existence and metadata consistency in `data/telemetry.db`.

---

## 2. Feature Inventory: 360-Degree Telemetry Audit

| Feature ID | Scope | Target Deliverable | Description | Verification Target |
|:---|:---|:---|:---|:---|
| **F1** | Database Integrity | `data/telemetry.db` | Telemetry database exists, connects, defines 4 tables (`sessions`, `steps`, `tool_calls`, `user_interventions`), and contains verified row populations (1,720 sessions, 387,426 steps, 236,847 tool calls, 3,270 interventions). | `TestTier1FeatureCoverage.test_t1_01_*` |
| **F2** | Pipeline Importability | `pipeline/*.py` | Core analytical modules in `pipeline/` (`classify_failures`, `analyze_context_dynamics`, `summarize_interventions`, `analyze_volume_distributions`, `analyze_ultra_deep_sessions`, `analyze_failure_clusters`, `benchmark_reasoning_tiers`, `inventory_customizations`, `audit_artifacts`, `audit_project_configs`) import cleanly and expose callable analysis interfaces. | `TestTier1FeatureCoverage.test_t1_02_*` |
| **F3** | Hermetic Execution | `pipeline/*.py` | Pipeline modules execute hermetically against clean-room mock databases without unhandled exceptions. | `TestTier1FeatureCoverage.test_t1_03_*` |
| **F4** | Report Section Structure | `docs/reports/360_telemetry_audit_2026_10.md` | Audit synthesis report contains all 5 mandatory canonical sections: Executive Summary, Multi-Agent Topologies, Operator Resilience, Tool-Failure Disconnect, and Recommendations. | `TestTier1FeatureCoverage.test_t1_04_*`<br>`TestTier2BoundaryAndCornerCases.test_t2_02_06_*` |
| **F5** | JSON Cache Integrity | `data/*.json` | Intermediate analysis caches exist, parse as valid JSON, and contain required metadata and operational statistics. | `TestTier1FeatureCoverage.test_t1_05_*`<br>`TestTier4RealWorldAcceptance.test_t4_01_02_*` |
| **F6** | Boundary & Query Safety | SQLite Queries | Database query logic gracefully handles 0-result tables, edge-case tokens, metacharacters, and double-ingested path deduplication. | `TestTier2BoundaryAndCornerCases.test_t2_01,07,08_*` |
| **F7** | Mathematical Consistency | Report ↔ Database | Verified metrics cited in the audit report match exact database query totals (1,720 sessions, 387,426 steps, 236,847 tool calls, 3,270 interventions, 26 preceding tool failures). | `TestTier3CrossFeatureVerification.test_t3_01,02,05_*` |
| **F8** | Cited Session Grounding | Report ↔ Database | Verified cited sessions (`495022c7`, `4021bbec`, `e072971e`, `8cbe936a`, `badb7661`, `6b8db4b5`) exist in `data/telemetry.db` with matching step counts, durations, and models. | `TestTier3CrossFeatureVerification.test_t3_03,04_*` |
| **F9** | Real-World Acceptance | Deliverable Bundle | End-to-end audit artifact validation, header compliance, lack of placeholder tokens, and production clearance. | `TestTier4RealWorldAcceptance.test_t4_03_*` |

---

## 3. 4-Tier Test Architecture

```
                    ┌────────────────────────────────────────┐
                    │      Tier 4: Real-World Acceptance     │
                    │ (Artifact Validation, Cache Alignment) │
                    └───────────────────▲────────────────────┘
                                        │
                    ┌───────────────────┴────────────────────┐
                    │  Tier 3: Cross-Feature Verification    │
                    │ (Mathematical Check, Cited Sessions)   │
                    └───────────────────▲────────────────────┘
                                        │
                    ┌───────────────────┴────────────────────┐
                    │     Tier 2: Boundary & Corner Cases    │
                    │ (Zero-Row DB, Missing Section Traps)   │
                    └───────────────────▲────────────────────┘
                                        │
                    ┌───────────────────┴────────────────────┐
                    │       Tier 1: Feature Coverage         │
                    │ (DB Tables, Pipeline Modules, Sections)│
                    └────────────────────────────────────────┘
```

### 3.1 Tier 1: Feature Coverage (`tests/test_audit_report.py::TestTier1FeatureCoverage`)
Validates that each core deliverable meets its baseline contract:
- `test_t1_01_telemetry_db_exists_and_connects`: Validates `data/telemetry.db` file presence, SQLite connection, 4 active tables (`sessions`, `steps`, `tool_calls`, `user_interventions`), and expected row counts.
- `test_t1_02_pipeline_modules_import_cleanly`: Validates that all 10 analytical pipeline modules in `pipeline/` import cleanly without runtime or dependency errors.
- `test_t1_03_pipeline_hermetic_execution`: Validates hermetic execution of pipeline analysis functions (`summarize_interventions`) using an isolated in-memory/temp SQLite schema.
- `test_t1_04_audit_report_required_sections_when_present`: Validates that `docs/reports/360_telemetry_audit_2026_10.md` (when present) or the canonical audit report template contains all 5 required canonical sections.
- `test_t1_05_intermediate_caches_exist_and_valid_json`: Validates that all refreshed `data/*.json` intermediate caches exist, parse cleanly, and contain non-empty data structures.

### 3.2 Tier 2: Boundary & Corner Cases (`tests/test_audit_report.py::TestTier2BoundaryAndCornerCases`)
Adversarially probes failure paths, empty datasets, and malformed inputs:
- `test_t2_01_empty_database_handling`: Confirms analysis functions handle empty SQLite tables (0 rows) gracefully without `ZeroDivisionError` or unhandled exceptions.
- `test_t2_02_report_validator_missing_executive_summary`: Confirms report validation catches omitted "Executive Summary" section.
- `test_t2_03_report_validator_missing_multi_agent`: Confirms report validation catches omitted "Multi-Agent Topologies" section.
- `test_t2_04_report_validator_missing_operator_resilience`: Confirms report validation catches omitted "Operator Resilience" section.
- `test_t2_05_report_validator_missing_tool_failure_disconnect`: Confirms report validation catches omitted "Tool-Failure Disconnect" section.
- `test_t2_06_report_validator_missing_recommendations`: Confirms report validation catches omitted "Recommendations" section.
- `test_t2_07_database_query_edge_case_tokens`: Confirms parameterized queries safely handle SQL metacharacters, unicode, and non-existent session IDs without crashes.
- `test_t2_08_double_ingestion_anonymization_filter_boundary`: Confirms query logic correctly filters double-ingested tool calls (`arguments_snippet NOT LIKE '%[WORKSPACE_ROOT]%'`).

### 3.3 Tier 3: Cross-Feature Verification (`tests/test_audit_report.py::TestTier3CrossFeatureVerification`)
Executes mathematical reconciliation and relational integrity verification between the database and reporting claims:
- `test_t3_01_mathematical_cross_check_session_and_step_counts`: Verifies exact database metrics: 1,720 sessions, 387,426 steps, 236,847 tool calls, and 3,270 interventions.
- `test_t3_02_mathematical_cross_check_tool_failure_disconnect`: Verifies the Tool-Failure Disconnect discovery: exactly 26 of 3,270 interventions (0.8%) followed a tool failure (>99.2% cognitive/governance).
- `test_t3_03_cited_sessions_exist_in_telemetry_db`: Verifies that key historical sessions cited in the report (`495022c7`, `4021bbec`, `e072971e`, `8cbe936a`, `badb7661`, `6b8db4b5`) exist in `sessions`.
- `test_t3_04_cited_sessions_metadata_cross_reference`: Verifies metadata properties of cited sessions (step counts, models, and dates matching survey records).
- `test_t3_05_report_metrics_cross_check_consistency`: Verifies that metric cross-checkers detect numerical discrepancies between reported values and database truth.

### 3.4 Tier 4: Real-World Acceptance (`tests/test_audit_report.py::TestTier4RealWorldAcceptance`)
Performs final end-to-end deliverable audit and cache synchronization validation:
- `test_t4_01_cache_and_db_alignment`: Cross-references intermediate cache totals (`operator_interventions_summary.json`, `classified_failures.json`) against live database counts.
- `test_t4_02_titan_sessions_cache_consistency`: Cross-references the 51 extreme titan sessions (>=1,000 steps) in `ultra_deep_sessions_analysis.json` against database queries.
- `test_t4_03_end_to_end_audit_artifact_validation`: Validates synthesis report markdown compliance (SPDX header, absence of placeholder tokens `[TBD]`, `TODO`, `FIXME`, and section completeness).

---

## 4. Test Suite Directory Layout

```
tests/
├── test_audit_report.py            # Primary 4-tier audit test suite (21 tests)
├── test_pipeline_audit_smoke.py    # Pipeline hermetic smoke tests
├── e2e/                            # Opaque-box CLI & hook tests
│   ├── harness_base.py
│   ├── test_tier1_features.py
│   ├── test_tier2_boundaries.py
│   ├── test_tier3_combinations.py
│   └── test_tier4_scenarios.py
└── ...
```

---

## 5. Runner Invocations & Benchmark Budgets

### Explicit Runner Commands

```bash
# 🧪 Run Complete Telemetry Audit Test Suite
python3 -m unittest tests/test_audit_report.py -v

# 🧪 Run Complete Repository Test Suite
python3 -m harness.cli test

# 🧪 Standard Unittest Discovery
python3 -m unittest discover -s tests -p "test_*.py"
```

### Benchmark Budgets

| Test Suite Tier | Test Count | Maximum Runtime Budget | Hermeticity Requirement |
|:---|:---|:---|:---|
| **Tier 1: Feature Coverage** | 5 tests | < 0.4s | Read-only DB queries / In-memory tempdir |
| **Tier 2: Boundary & Corner Cases** | 8 tests | < 0.3s | In-memory SQLite / Clean-room tempdir |
| **Tier 3: Cross-Feature Verification** | 5 tests | < 0.3s | Parameterized read-only DB queries |
| **Tier 4: Real-World Acceptance** | 3 tests | < 0.3s | Read-only cache & artifact validation |
| **Complete Audit Suite** | **21 tests** | **< 1.0s** | **Zero Network / External Deps** |

---

## 6. Requirement Traceability Matrix

| Requirement | Target Deliverable | Test Class & Methods |
|:---|:---|:---|
| **R1: Telemetry Ingestion & Pipeline** | `data/telemetry.db`, `pipeline/*.py`, `data/*.json` | `TestTier1FeatureCoverage.test_t1_01_02_03_05`<br>`TestTier2BoundaryAndCornerCases.test_t2_01_07_08`<br>`TestTier4RealWorldAcceptance.test_t4_01_02` |
| **R2: Multi-Agent & Topologies** | `/teamwork-preview`, `/boost`, `/subagent-ladder`, Titan sessions | `TestTier1FeatureCoverage.test_t1_04`<br>`TestTier3CrossFeatureVerification.test_t3_03_04`<br>`TestTier4RealWorldAcceptance.test_t4_02` |
| **R3: Operator Resilience & Steering** | Tool-Failure Disconnect, ADR enforcement, Powerloss, Pause/Resume | `TestTier1FeatureCoverage.test_t1_04`<br>`TestTier3CrossFeatureVerification.test_t3_02_03`<br>`TestTier4RealWorldAcceptance.test_t4_01` |
| **R4: 360-Degree Synthesis Report** | `docs/reports/360_telemetry_audit_2026_10.md` | `TestTier1FeatureCoverage.test_t1_04`<br>`TestTier2BoundaryAndCornerCases.test_t2_02_03_04_05_06`<br>`TestTier3CrossFeatureVerification.test_t3_05`<br>`TestTier4RealWorldAcceptance.test_t4_03` |

---

## 7. Publication Protocol for `TEST_READY.md`

When the audit verification suite is implemented and validated:
1. `tests/test_audit_report.py` must contain all 4 tiers with 100% passing tests.
2. Full repository test suite (`python3 -m harness.cli test`) must pass with exit code 0.
3. Execution time of `tests/test_audit_report.py` must be strictly under 1.0s.
4. `TEST_READY.md` must be updated at repository root with exact test counts, pass rates, runner commands, and coverage verification.
