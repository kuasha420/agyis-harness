# Project: 360-Degree Telemetry Audit & Emergent Pattern Mining

## Architecture
- **Data Layer (`data/`)**: SQLite telemetry databases (`data/telemetry.db`, `data/telemetry_hub.db`), intermediate analysis JSON caches (`data/*.json`).
- **Telemetry Infrastructure (`harness/telemetry/`)**: Schema definition (`schema.py`), bidirectional multi-node sync engine (`sync/push.py`, `sync/pull.py`, `sync/coordinator.py`).
- **Analytical Pipeline (`pipeline/`)**: Dedicated forensic modules (`extract_transcripts.py`, `classify_failures.py`, `analyze_ultra_deep_sessions.py`, `analyze_failure_clusters.py`, `analyze_volume_distributions.py`, `analyze_context_dynamics.py`, `summarize_interventions.py`, `audit_artifacts.py`, `audit_project_configs.py`).
- **CLI Dispatcher (`harness/commands/audit.py`, `harness/cli.py`)**: `./agyis audit <stage>` and `python3 -m harness.cli audit <stage>`.
- **Reporting Deliverables (`docs/reports/`)**: Permanent evidence-grounded report at `docs/reports/360_telemetry_audit_2026_10.md`.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Full Pipeline Ingestion & Execution | Run full audit pipeline (`extract`, `classify`, `dynamics`, `interventions`, `volume`, `deep`, `clusters`) with exit code 0 | M1 | Survey 1 / R1 |
| 2 | Cache Reconciliation & Stale Cache Refresh | Refresh stale caches (`artifacts_audit_summary.json`, `project_configs_audit.json`, `top_100_cognitive_trajectories.json`) | M1 | Survey 1 / R1 |
| 3 | Double-Ingestion Duplication Documentation | Document the 623-session duplication anomaly and provide mathematical dedup filters | M1 | Survey 1 / R1 |
| 4 | Native `/teamwork-preview` Topology Dissection | Analyze evolution (prototype -> July 29-subagent swarm -> Oct resilient dual-gen) | M2 | Survey 2 / R2 |
| 5 | High-Intensity `/boost` Modality Analysis | Dissect 346 `/boost` interventions, reasoning mode selection, and 4k char thinking spans | M2 | Survey 2 / R2 |
| 6 | Agyis `/subagent-ladder` Pipeline Analysis | Trace historical inception (Session `4021bbec`, 101.5h) and 4-stage ladder protocol | M2 | Survey 2 / R2 |
| 7 | Cognitive Cliff & Titan Session Dynamics | Quantify error/intervention escalation (<20k vs >100k vs >200k) and tool shift in titan sessions | M2 | Survey 2 / R2 |
| 8 | Subagent Latency & Coordination Profiles | Profile subagent dispatch (0.05s) vs background task sync (1.26s) and blockage risks | M2 | Survey 2 / R2 |
| 9 | Tool-Failure Disconnect Discovery | Document finding that only 26 of 3,270 (0.8%) interventions followed tool errors | M3 | Survey 3 / R3 |
| 10 | Flight Director Steering & Drift Mitigation | Categorize 55 interventions for monorepo drift, generative overfit, and synthetic status | M3 | Survey 3 / R3 |
| 11 | ADR Invariant Enforcement Analysis | Document 112 interventions enforcing ADR-012, ADR-013, ADR-015, ADR-028 | M3 | Survey 3 / R3 |
| 12 | Pause & Resume Lifecycle Invariants | Analyze 222 pause/park alerts, 78 resumes, and the "Never Kill Subagents During Pause" rule | M3 | Survey 3 / R3 |
| 13 | Disaster & Powerloss Recovery Signatures | Document 106 events: Bangladesh load shedding, `/powerloss-resume`, Linux OOM crashes | M3 | Survey 3 / R3 |
| 14 | 360-Degree Comprehensive Synthesis Report Authoring | Compile complete evidence-grounded report at `docs/reports/360_telemetry_audit_2026_10.md` | M4 | Survey 1-3 / R4 |
| 15 | Harness & Cockpit Strategic Recommendations | Codify 5 concrete recommendations (Anti-Kill Hook, Powerloss Resume Skill, Quota Burn Gauges, Memory Throttling, Dual Gate Auditor) | M4 | Survey 1-3 / R4 |
| 16 | Comprehensive E2E Verification Suite | Automated verification of pipeline execution, report structure, and telemetry claims | E2E | R1-R4 / Acceptance |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Pipeline Ingestion & Cache Reconciliation | Run all audit pipeline stages, reconcile DB records, update `data/*.json` | None | DONE |
| M2 | Multi-Agent & Topology Dissection Verification | Validate multi-agent, boost, ladder, and cognitive cliff metrics | M1 | DONE |
| M3 | Operator Steering & Resilience Dissection Verification | Validate steering, ADR invariants, pause/resume, and disaster recovery metrics | M1 | DONE |
| M4 | 360-Degree Comprehensive Synthesis Report Authoring | Author `docs/reports/360_telemetry_audit_2026_10.md` | M2, M3 | DONE |
| M5 | E2E Verification & Out-of-Band Audit Gate | Run E2E verification test suite, reviewer, challenger, and forensic auditor | M4 | DONE |

## Interface Contracts
### Analytical Pipeline ↔ Data Caches
- Pipeline scripts output clean, formatted JSON files in `data/*.json`.
- Analytical caches record standard analytical keys and summary metrics (e.g. `overview`, `total_interventions`, `timestamp` / `generated_at`).
- Database queries must handle double-ingested tool calls gracefully using deduplication keys or raw session counts.

### Data Caches ↔ Comprehensive Synthesis Report
- Every metric, table, and percentage in `docs/reports/360_telemetry_audit_2026_10.md` must link to a verified query in `data/telemetry.db` or a field in `data/*.json`.
- Every cited session must include `session_id`, step index, timestamp, and context summary.

## Code Layout
- `pipeline/`: Analytical scripts. Owned by Worker M1.
- `data/`: Database and cache files. Managed by Worker M1.
- `docs/reports/360_telemetry_audit_2026_10.md`: Authoritative synthesis deliverable. Owned by Worker M4.
- `tests/test_audit_report.py`: E2E verification suite. Owned by E2E Test Writer.
