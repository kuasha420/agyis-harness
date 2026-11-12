<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Agyis Harness Project Ledger (Compacted Post-RC10 Horizon 0)

> **Historical Archive**: Phases 1–35 (2026-10-02 through `v1.0.0-rc10`) live verbatim at `0069329:docs/archive/ledger/project-ledger-rc10-historical.md` (indexed in [`docs/archive/README.md#ledger`](../archive/README.md#ledger)).
> **Authoritative Baselines**: Reconciled empirical metrics and Route A/B/C scores live in [`docs/taxonomy/empirical-baselines.md`](empirical-baselines.md).
> **Architecture Registry**: Decisions `ADR-001` through `ADR-035` are maintained in [`docs/adr/README.md`](../adr/README.md).

---

## 1. Current Release Baseline (`v1.0.0-rc10` — 2026-11-10)

- **Automated Verification**: **1,993 hermetic tests** passing in ~66s (`python3 -m harness.cli test`), with sub-second isolated module benchmarks (`<0.02s–0.75s`).
- **Architectural Fitness Function**: **100.0/100 AFF score** (`python3 -m harness.cli audit aff`), enforcing Product vs. Project isolation (`ADR-014`), DAG import acyclicity, bounded caches, and external asset separation (`PSL-INV-011`).
- **Cleanroom Specification Gate**: Typed obligation ledgers and immutable SHA-256 evidence records verified cleanly via `python3 -m harness.cli verify --spec` and `agyis verify`.
- **Single-Source Hygiene Gate**: `tests/test_skills_dedup_gate.py` + `harness/runtime/hygiene_checks.py` require `.agents/skills/` mirrors of `harness/skills/` to be symlinks (`../../harness/skills/<name>`), saving `~4,500` prompt tokens/turn across Layer 1–3 precedence.
- **Documentation Separation**: Legacy empirical reports, RFCs, telemetry audits, and discovery notes are compacted out of active context per `ADR-003` and frozen at commit `0069329` (indexed in [`docs/archive/README.md`](../archive/README.md)).

---

## 2. Active System Architecture Pillars

| Domain | Canonical Mechanism & Code Surfaces | Controlling Specs / ADRs |
| :--- | :--- | :--- |
| **Product Bifurcation** | Distributable zero-dependency `harness/` strictly decoupled from experimental `pipeline/`, `data/`, `tests/`, and `docs/` | `ADR-014`, `ADR-015` |
| **Output Compaction** | `PostToolUse` 2KB smart compactor (`head 500B` + `tail 1,000B` + fatal/error extraction) with zero error-truncation invariant | `ADR-007`, `ADR-008` |
| **Runtime Determinism** | `PreToolUse` `uv` CPython `>=3.12` injection, SSH `BatchMode` timeouts, inline script hygiene guard, `PSL_HARNESS_STATE_DIR` state isolation | `ADR-023`, `PSL-INV-002` |
| **Loop & Drift Control** | `PreToolUse` repeated-call breaker, plan-boundary/auditor write fence, persona truth gate, `PreInvocation` `230k`/`180k` advisory, `Stop` gate (`code_dirty` vs `spec_dirty`) | `ADR-009`, `ADR-024`, `ADR-032`, `ADR-033` |
| **Cockpit & Swarm** | Root Flight Director (`agyis cockpit`), 12 workflows (`agyis router`/`ladder`), checkpoints & parking, `agyis subagents --liveness`, dual-auditor `audit_verdict.json` gate | `ADR-025`, `ADR-031A`, `ADR-033`, `PSL-INV-008` |
| **Custom Subagents** | Validated frontmatter (`17` static `ANTIGRAVITY_PLATFORM_TOOLS` + `3` dynamic `permissions.mcp` primitives = `20`-tool ceiling, zero-hang contract) for `agyis_investigator`, `agyis_architect`, `agyis_builder`, `agyis_reviewer`, `agyis_custodian`, `agyis_auditor` | `ADR-026`, Issue `#97` |
| **Cleanroom & REA** | `.dirtyroom/` Ghidra `-noanalysis -readOnly` pre-analyzed cache (`<2s` SLA), `agyis re` (`init`, `patch-rea`, `pre-analyze`, `find`, `decompile`, `pcap`), typed obligation ledgers (`harness/cleanroom/`) | `ADR-028`, `PSL-INV-007`, `PSL-INV-009` |
| **Delivery & Extensions** | Branch-isolated `agyis onboard` / `init` / `harmonize`, fork topology routing, port `5432` collision guard, `agyis sync` daemon, `.agents/commands/` extensions (`agyis ext`) | `ADR-027`, `ADR-030`, `ADR-031B`, `ADR-034` |

---

## 3. Compacted RC Milestone Chronology (Phases 1–35)

| Epoch / Release | Date | Architectural Inflection Summary | Verified Test Baseline |
| :--- | :---: | :--- | :---: |
| **Phases 1–5.3** | 2026-10-02 | SQLite `telemetry.db`, Dynamic Aperture (`ADR-003`), POC `PostToolUse` 2KB compactor, `uv` CPython 3.12 injection, modular skills & CLI | `67` tests (`0.932s`) |
| **Phases 1–10 (Core)** | 2026-10-02–05 | Deterministic `Stop` completion fence, `ADR-023`–`026`, `ADR-030`–`032`, telemetry gateway (`server/`), custom subagents, anti-drift | `237+` tests |
| **`v1.0.0-rc4` (Ph 11)** | 2026-10-16 | Dynamic Repository Awareness (DRA) runner detection, initial cleanroom REA integration, single-source plugin skills | `847` tests (`12.7s`) |
| **`v1.0.0-rc5` (Ph 12–14)** | 2026-10-17–18 | 18-repo fleet harmonization (`onboard`, port collision), Electron Trajectory Debug View (`agyis gui`), noise-free test runner | `1,065` tests (`20.2s`) |
| **`v1.0.0-rc6` (Ph 15–16)** | 2026-10-18 | Automated release manifest tooling, `360_telemetry_audit_2026_10.md` baseline snapshot (`N=1,720` sessions) | `1,115` tests (`19.5s`) |
| **Phases 17–29 (`rc7` Dev)** | 2026-10-18–26 | Anti-synthetic verification (`#51`), carrier-grade compaction & native succession (`ADR-031A`), Cockpit/Router harmonization, DB pruning (`#56`) | `1,120` -> `1,608+` |
| **`v1.0.0-rc7` (Ph 30)** | 2026-10-27 | Closed 19/19 resilience/safety/cognitive issues (`#64`, `#69`, `#74`), single-source rule dedup, persona truth, dual-gate auditor fence | `1,729` tests (`17.18s`) |
| **`v1.0.0-rc8` (Ph 31–33)** | 2026-10-27–28 | Native REA 6.8.0 schema/JDK healing (`#96`), granular MCP scoping & shell hygiene hook (`#97`), ELF/Rust cleanroom verification, worktree prune | `1,770` tests (`18.39s`) |
| **`v1.0.0-rc9` (Ph 34)** | 2026-11-03 | `256k/230k/180k` cockpit thresholds & de-spammed advisory (`ADR-033`), pre-analyzed Ghidra cache (`PSL-INV-009`), extensible CLI (`ADR-034`) | `1,782` tests (`17.4s`) |
| **`v1.0.0-rc10` (Ph 35)** | 2026-11-10 | In-tree symlink skill deduplication gate, `ADR-031A/B` disambiguation, `28` current top-level CLI subcommands (`router` & `ladder` separate), **100.0/100 AFF** release gate | `1,981` tests (`~65s`) |
| **Post-RC10 (`ADR-035`)** | 2026-11-12 | Unified `harness/trajectory/` SSOT (epoch splitting, burn rate, honest `unattributed` tokens, scaled subagent health), modular HUD assets, daemon/command-safety fixes (#107–#112), tightened `800L / 25D / 0 @aff_exempt` AFF gate | Verified pre-release |
| **Phase 36 (Cleanroom Parity)** | 2026-11-12 | Trajectory HUD & SSOT Stock 2.26.0 Parity: 9 modular cleanroom frontend assets (<800L), 0-token unattributed gap (protobuf `tokenBreakdown.groups`), dynamic pane focus & subagent traversal (1-click `← Parent` pill, `/c/:id` freshness), 60 FPS ConnectRPC streaming | 2,032 tests (50.06s), AFF 100/100 (`b3ecad7`) |

---

## 4. Active Post-RC10 Governance Invariants (`PSL-INV-001`–`011`)

1. **Automated Verification (`PSL-INV-001`)**: Every completion claim requires exit-0 `python3 -m harness.cli test`, `verify --spec`, and `audit aff`; build caches (`.next/`, `.turbo/`, `node_modules/.cache`) must be purged before verification gates.
2. **Terminal & Edit Safety (`PSL-INV-002`, `003`)**: Multi-line inline scripts belong in `scratch/`; zero-match pattern probes handle `|| [ $? -eq 1 ]`; targeted edits use contiguous `replace_file_content`.
3. **Context Preservation (`PSL-INV-004`, `005`)**: Enforce reactive wait without status/log polling, maintain single-source Layer 1–3 skill hygiene, and compact milestone ledgers (`<50` lines/phase) via Dynamic Sliding Aperture.
4. **Human-in-the-Loop Alignment (`PSL-INV-006`)**: Anchor implementation strictly to approved artifacts; pause for destructive actions or repeated command failures (`>=2`).
5. **Cleanroom & Decompiler Cache (`PSL-INV-007`, `009`)**: Quarantine `.dirtyroom/` caches away from VCS; execute Ghidra with `-noanalysis -readOnly` (`<2s` SLA); resolve unknowns solely via typed obligation ledgers + SHA-256 evidence.
6. **Cockpit & Anti-Vibe Governance (`PSL-INV-008`, `010`)**: Root Flight Director delegates without code thrash through dual-auditor certification; dynamic UI/HUD tooling tracks live SPA routes and purges stale DOM on re-mount.
7. **Architectural Fitness (`PSL-INV-011`)**: Enforce zero cross-layer boundary breaches (`harness/` -> `pipeline/` banned), externalize non-native assets, cap in-memory caches, and keep import graphs strictly acyclic.

---

## 5. Canonical Release Gate Commands

```bash
python3 -m harness.cli test          # Complete hermetic suite (1,993 tests, ~66s)
python3 -m harness.cli verify --spec # Cleanroom specification claim + SHA-256 evidence gate
python3 -m harness.cli audit aff     # Architectural fitness function gate (100.0/100 AFF)
python3 -m harness.cli doctor        # 3-tier runtime, port 5432, hook & plugin diagnostics
python3 -m harness.cli rules --lint  # Agent rule formatting & duplicate check
```

---

## 6. Open Post-RC10 Trackers

- **Deferred Scope**: `ADR-029` remains explicitly deferred post-RC10 per [`docs/adr/README.md`](../adr/README.md).
- **Active Post-RC10 Consolidation**:
  - Historical doc archival & PII scrubbing across `docs/archive/` (Wave 1 complete; empirically reconciled in [`empirical-baselines.md`](empirical-baselines.md)).
  - Master ADR registry consolidation, pipeline report repointing, cleanroom/official spec compaction, runbook deduplication, and skill `<24KB` + ToC gating.
