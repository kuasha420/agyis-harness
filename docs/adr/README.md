<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Architecture Decision Records (ADR) Catalog

**Project**: PSL Harness for Google Antigravity™ (`psl-agy-harness`)  
**Publisher**: Purrfect Software Limited (PSL)  
**License**: Apache-2.0  
**Scope**: Complete Architectural Decision Records Index (ADR-001 through ADR-032)  
**Last Updated**: 2026-10-10  

---

## Executive Summary

This catalog preserves the architectural history, design trade-offs, and behavioral invariants governing `psl-agy-harness`. Historical decisions across Horizons 0 and 1 are compacted in `../taxonomy/project-ledger.md` in accordance with ADR-003 (Dynamic Aperture Planning), while major standalone decision specifications are preserved as individual records.

---

## Canonical ADR Index

| ADR | Title | Status | Date | Primary Location | Summary |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **ADR-001** | Open Source Stance & Platform Alignment | Accepted | 2026-10-02 | [project-ledger.md](../taxonomy/project-ledger.md) (Phase 1) | Apache-2.0 license. Build on and extend official Antigravity surfaces rather than building a competing runtime. |
| **ADR-002** | Structured Telemetry Schema | Accepted | 2026-10-02 | [project-ledger.md](../taxonomy/project-ledger.md) (Phase 1) | SQLite database (`data/telemetry.db`) mapping sessions, steps, tool calls, and human interventions. |
| **ADR-003** | Dynamic Aperture Planning | Accepted | 2026-10-02 | [resolution-gradient-architecture.md](../taxonomy/resolution-gradient-architecture.md) | Resolution Gradient with Retroactive Horizon Compaction: high-res present, mid/low-res future, compacted permanent ledger. |
| **ADR-004** | Extension Surface Bifurcation | Accepted | 2026-10-02 | [platform-surface-mapping.md](../official-specs/platform-surface-mapping.md) | Three-tier boundary: Tier 1 Native Platform Primitives, Tier 2 Deterministic Lifecycle Hooks, Tier 3 External Services (MCP). |
| **ADR-005** | Reactive Wakeup Supremacy | Accepted | 2026-10-02 | [project-ledger.md](../taxonomy/project-ledger.md) (Phase 3) | Prohibits polling `manage_task(Action='status')` in favor of event-driven reactive messaging wakeups. |
| **ADR-006** | PreToolUse Argument Rewrite Interception | Accepted | 2026-10-02 | [platform-surface-mapping.md](../official-specs/platform-surface-mapping.md) | Standardized on `PreToolUse` shallow `overwrite` dictionaries to sanitize commands, inject pagers, and add timeouts. |
| **ADR-007** | Deterministic 2KB Output Compactor | Accepted | 2026-10-02 | [output-compactor-poc-results.md](../taxonomy/output-compactor-poc-results.md) | PostToolUse compaction for `run_command` and `view_file`: preserves 500 chars head, 1,000 chars tail, and error lines. |
| **ADR-008** | Diagnostic Failure Preservation Invariant | Accepted | 2026-10-02 | [project-ledger.md](../taxonomy/project-ledger.md) (Phase 4) | Invariant: Any tool execution with non-zero exit code or error status is preserved 100% in full without compaction. |
| **ADR-009** | Cognitive Circuit Breaker | Accepted | 2026-10-02 | [project-ledger.md](../taxonomy/project-ledger.md) (Phase 2) | PreToolUse loop tripping when consecutive tool calls lack parameter mutation, breaking the Repetition Trap. |
| **ADR-010** | Attention Sink Desync Fence | Accepted | 2026-10-02 | [project-ledger.md](../taxonomy/project-ledger.md) (Phase 2) | Detects attention sink collapse (e.g. 85.5% thought perseveration) and forces state synchronization before runaway step counts. |
| **ADR-011** | Hermetic Runtime Guarantee | Accepted | 2026-10-02 | [project-ledger.md](../taxonomy/project-ledger.md) (Phase 4.2) | Transparently injects uv CPython >= 3.12 for inline utility one-liners (`python3 -c`), eliminating PEP 701 syntax crashes. |
| **ADR-012** | Artifact-First Planning Invariant | Accepted | 2026-10-02 | [.agents/rules/AGENTS.md](../../.agents/rules/AGENTS.md) | Prohibits architectural proposals in raw chat turns. All non-trivial changes must crystallize into `implementation_plan.md`. |
| **ADR-013** | Surgical Shell Pattern Probing Exception | Accepted | 2026-10-02 | [.agents/rules/AGENTS.md](../../.agents/rules/AGENTS.md) | Standalone pattern searches (`grep`/`diff`) without conditionals append `\|\| [ $? -eq 1 ]` to neutralize empty-match failures. |
| **ADR-014** | Product vs. Project Bifurcation | Accepted | 2026-10-02 | [project-ledger.md](../taxonomy/project-ledger.md) (Phase 5.1) | Strict separation between distributable runtime (`harness/`) and development telemetry laboratory (`pipeline/`, `data/`). |
| **ADR-015** | Clean-Room Testing & Hermetic Isolation | Accepted | 2026-10-02 | [testing-contracts.md](../official-specs/testing-contracts.md) | Mandatory hermetic isolation (`tempfile`), sub-second benchmark execution (<1.0s), and protojson contract verification. |
| **ADR-016** | Standalone Fail-Safe Hook Dispatcher | Accepted | 2026-10-02 | [runner.py](../../harness/hooks/runner.py) | Direct module mapping in `runner.py` with top-level try/except fail-open deadlock protection (`{"decision":"allow"}`). |
| **ADR-017** | Progressive Stack Disclosure | Accepted | 2026-10-02 | [project-ledger.md](../taxonomy/project-ledger.md) (Phase 5.2) | Offloads stack-specific rules from monolithic prompts into on-demand modular skills (`harness/skills/`), preserving context. |
| **ADR-018** | Specialist Subagent Archetypes | Accepted | 2026-10-02 | [subagents/](../../harness/subagents/) | Codified bounded specialist archetypes with `can_subagent=False` to eliminate runaway recursive subagent trees. |
| **ADR-019** | Multi-Agent Subagent Ladder Pipeline | Accepted | 2026-10-02 | [skills/subagent-ladder/](../../harness/skills/subagent-ladder/) | Multi-agent SWE execution ladder (`Executioner -> Hammer -> Auditor`) with anti-bypass and zero-remediation invariants. |
| **ADR-020** | Empirical Volume Telemetry Schema | Accepted | 2026-10-02 | [project-ledger.md](../taxonomy/project-ledger.md) (Phase 5.3) | Non-destructive schema migration capturing output characters, lines, argument lengths, and command categories. |
| **ADR-021** | Failure Compaction Exemption Audit | Accepted | 2026-10-02 | [tool-volume-distribution-report.md](../taxonomy/tool-volume-distribution-report.md) | Validated empirical compaction simulation across 64,065 calls, proving 0 violations of Failure Preservation Invariant. |
| **ADR-022** | Stop-Hook Verification Fence State Machine | Accepted | 2026-10-02 | [project-ledger.md](../taxonomy/project-ledger.md) (Horizon 1 Phase 1) | Gated completion on clean `agyis test` execution with 2-block anti-deadlock safety valve and PreToolUse dirty tracking. |
| **ADR-023** | Terminal Execution & Subshell PATH Reliability | Accepted | 2026-10-02 | [lifecycle-hooks.md](../official-specs/lifecycle-hooks.md) (§3.2) | Recovers toolchain PATH shims for non-login subshells; injects non-blocking SSH timeouts to prevent background hangs. |
| **ADR-024** | Plan-to-Execution Anti-Drift Gate | Accepted | 2026-10-03 | [lifecycle-hooks.md](../official-specs/lifecycle-hooks.md) (§3.3) | Intercepts mutations against declared plan targets with multi-resolution matching and document/scratch exemptions. |
| **ADR-025** | Subagent Ergonomics & Zero-Token Context Gauge | Accepted | 2026-10-03 | [lifecycle-hooks.md](../official-specs/lifecycle-hooks.md) (§5) | Evaluates subagent token consumption in microseconds; enforces Auditor write-block guard and Zero-Exploration Invariant. |
| **ADR-026** | Custom Codebase & Workspace-Aware Agents | Accepted | 2026-10-03 | [custom-agents.md](../official-specs/custom-agents.md) | Dual-mode discovery (subagent + UI entrypoint); model inheritance; 20-tool catalog validation preventing platform hang. |
| **ADR-027** | Remote Execution & SSH Multiplexing Harness | Accepted | 2026-10-03 | [roadmap.md](../../roadmap.md) (Phase 7) | Transparent OpenSSH ControlMaster multiplexing; stdin script streaming; `<2KB` remote triage; remote pattern sanitization. |
| **ADR-028** | [Reserved: Multi-Node Linda Tuplespace Protocol] | Deferred | 2026-10-04 | [roadmap.md](../../roadmap.md) (Horizon 2) | Reserved for Knot mesh Linda Tuplespace batch coordination and barrier synchronization across hardware nodes. |
| **ADR-029** | [Reserved: Spatial Terminal Multiplexing] | Deferred | 2026-10-04 | [roadmap.md](../../roadmap.md) (Horizon 2) | Reserved for Confluence mode spatial terminal multiplexing and out-of-band GitHub Discussion coordination. |
| **ADR-030** | Global Plugin Delivery & Central Telemetry Hub | Accepted | 2026-10-05 | [delivery/](../../harness/delivery/), [server/](../../server/) | Three-tier resource precedence, Starlette telemetry gateway, GitHub Org authentication caching, chunked sync transport. |
| **ADR-031A** | Native Orchestration Alignment (Boost & Plan) | Accepted | 2026-10-05 | [ADR-031-native-orchestration-alignment.md](ADR-031-native-orchestration-alignment.md) | PreToolUse Native Plan-Mode Lock, dual taxonomy (Boost Swarm vs Subagent Ladder), adversarial verifier capability bundle. |
| **ADR-031B** | Unified Workspace Harmonization Lifecycle, Multi-Tier Presets & Delivery | Accepted | 2026-10-13 | [ADR-031-unified-workspace-harmonization.md](ADR-031-unified-workspace-harmonization.md) | Atomic 4-phase deprecation lifecycle (`--prune-legacy`), decoupled presets, monorepo scanner, fork-aware topology probe, and `onboard` CLI command. |
| **ADR-032** | Tool-Native Primacy & Task Log Anti-Polling | Accepted | 2026-10-10 | [ADR-032-tool-native-primacy-and-anti-polling.md](ADR-032-tool-native-primacy-and-anti-polling.md) | Strict Reactive Wait Invariant on `.system_generated/tasks/*.log`; Tool-Native Primacy rule; 8 modular ops runbooks. |
