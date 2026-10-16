<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Changelog

All notable changes to the `agyis-harness` project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0-rc4] - 2026-10-16

### Features & Architecture
- **feat(dra): Dynamic Repository Awareness & Friction Remediation** (PSL-SPEC-2026-DRA-001, PR #40)
  - Dynamically detects repository-native test runners (pytest, unittest, cargo, go test, npm/pnpm test) to eliminate testing friction.
  - Implements dynamic workspace root discovery and test runner gating.
  - Relaxes anti-loop guardrails to exempt heartbeat/coordination operations and introduce advisory status.
  - Eliminates f-string quote corruption and decouples grep tail in command safety hook.
  - Hardens harvester WAL concurrency and aligns shell subprocess runner.
- **feat(rea): Opt-In REA Cleanroom Reverse Engineering Architecture** (ADR-028, PR #48)
  - Introduces decoupled doctor diagnostics (`--experimental-rea`) with a 7-tier OpenJDK 21 discovery ladder and disassembler contract checks (Ghidra, Hopper, IDA, JADX).
  - Implements phase-aware cleanroom completion fence and non-interference lifecycle hooks.
  - Packages the `reverse-engineer-anything` modular skill and documentation.
  - Delivers a comprehensive 4-tier E2E test suite covering cleanroom boundaries, combinations, and scenarios.
- **feat(telemetry): Telemetry Sync Engine Hardening & Concurrency** (PR #39, closes #52)
  - SQLite WAL mode concurrency and decoupled mutex locks for background ingestion and synchronization.
  - Authenticated dry-run preview, cross-device watermarking, and bounded push memory batching.
  - Adds composite unique indexes, `executemany` batching, and accurate delta counting for robust pull/push replication.
- **feat(rules): Single-Source Skills Hygiene & Rule Bifurcation** (closes #52, #53)
  - Codifies rule bifurcation between global agent defaults (`GLOBAL_AGENTS.md`) and project-scoped rules (`.agents/rules/AGENTS.md`).
  - Implements single-source skills hygiene and automated duplicate pruning (`agyis skills --prune-duplicates`).
  - Adds `--dry-run` and `--config-dir` flags to `agyis skills` CLI parser.
- **feat(hooks): Lifecycle Hook Hardening & Issue Templates** (PR #47, closes #41-#46)
  - Exempts coordination and heartbeat files from anti-loop triggers.
  - Normalizes PostToolUse protojson output and hardens scratch path resolution.
  - Introduces typed GitHub Issue form templates (`bug_report.yml`, `feature_request.yml`, `config.yml`).

### Bug Fixes & Hardening
- **fix(hooks,cli): Shadow Audit Remediation (DEF-01..DEF-04)**
  - Remediates shadow audit findings across anti-loop cycle detection, completion fence validation, and hooks schema alignment.
  - Adds `agyis verify` command for cleanroom specification and obligation ledger validation.
- **fix(telemetry): Foreign Key Integrity & Batch Optimization**
  - Guards foreign keys during remote pulls and eliminates batching memory bloat.
- **fix(anti-loop): Degenerate Cycle Detection & Basename Matching**
  - Skips degenerate 1-step cycles in N-gram detector to allow consecutive idempotent operations.
  - Enforces exact basename matching for coordination files.
- **fix(hooks): Command Safety String Formatting & Protojson Normalization**
  - Fixes command safety hook f-string quoting corruption.
  - Standardizes protojson serialization for PostToolUse hook inputs.

### Maintenance & Release
- **chore(release): Version Bump to 1.0.0-rc4**
  - Synchronizes version `1.0.0-rc4` across all 9 manifest and test files.
  - Compiles release changelog and formalizes delivery packaging.

---

## [1.0.0-rc3] - 2026-10-14

### Features & Architecture
- Reconciled and merged `origin/work/poc-consolidated-preview` into main (scoped exit-255 socket recovery, telemetry sync boolean query parameters, state directory fallback hardening, subprocess runner tests).
- Implemented dynamic SPDX license header detection matching repository manifests.
- Added symlink write-through integrity and recursive link sanitization (`.agent/` -> `.agents/`).
- Decoupled test runner commands across 24 skill templates to respect repository-native test runners.

### Bug Fixes & Hardening
- Hardened compound SPDX regex parsing and symlink provisioning test isolation.
- Eradicated Ground Rule 1 string discrepancies across templates.

### Maintenance & Release
- Bumped version to `1.0.0-rc3`, updated package and plugin manifests, and synchronized lockfile.

---

## [1.0.0-rc2] - 2026-10-14

### Features & Architecture
- Implemented 4-phase atomic legacy deprecation and pruning lifecycle (`--prune-legacy`).
- Decoupled language runtimes from architectural roles and implemented bounded-depth monorepo scanning.
- Added fork-aware remote probing, PR tracking, and `agyis onboard` command (ADR-031 Track C).
- Authored 4 operational runbooks, formalized ADR-031, updated modular skills, and normalized nomenclature.

### Bug Fixes & Hardening
- Guarded dry-run git exclude mutation and handled 0-byte legacy rules.

### Maintenance & Release
- Bumped version to `1.0.0-rc2`, updated package and plugin manifests, and synchronized lockfile.

---

## [1.0.0-rc1] - 2026-10-13

### Bug Fixes & Hardening
- Replaced deprecated `datetime.utcnow` with `timezone.utc` across pipeline and hooks.
- Preserved sync status and origin developer on session re-harvest.
- Cleaned legacy plugin directory during upgrade migration.

---

## [1.0.0-rc0] - 2026-10-12

### Features & Initial Release
- Initial release candidate for Agyis Harness for Google Antigravity™.
- Autonomous agent runtime harness, empirical audit telemetry pipeline, and lifecycle hooks immune system.
