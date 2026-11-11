<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# ADR-031: Native Orchestration Alignment (Boost Swarm & Plan Mode)

* **Status**: Accepted (Finalized)
* **Date**: 2026-10-05 (Finalized 2026-10-06)
* **Authors**: Antigravity & PSL Lead Architect
* **Scope**: `harness/`, `pipeline/`, `docs/`

---

## Context & Motivation

Between versions **v1.1.0** and **v1.2.16**, Google Antigravity transitioned from a conversational pair-programmer to a **structured multi-agent operating system**. At the core of this transition are two native platform primitives:

1. **Native `/plan` Mode**: A pre-execution modal planning loop (`default` $\to$ `accept-edits` $\to$ `plan`) and prompt prefix (`/plan`) that enforces read-only exploration and the creation of an interactive `implementation_plan.md` artifact with `RequestFeedback: true` to gate workspace mutations.
2. **Native `/boost` Mode**: An on-demand multi-agent swarm orchestrator utilizing stigmergic blackboard coordination (`.swarm_blackboard_<task>.md`), worker auto-retry (up to 4 retries), a succession handoff protocol (at 16 spawns), and specialized worker personas (Deep Coding Agent, High-Reliability Reviewer, and Code-Executing Adversarial Verifier).

> [!NOTE] Architectural Decoupling: Native Primitives vs. Custom Agents
> Custom codebase-aware agents and the `/agent-builder` skill are **PSL harness features**, governed and codified separately under **ADR-026** ([`docs/official-specs/custom-agents.md`](../official-specs/custom-agents.md) and [`.agents/skills/agent-builder/SKILL.md`](../../.agents/skills/agent-builder/SKILL.md)). They are completely decoupled from native orchestration alignment (ADR-031) and plugin delivery (ADR-030).

Prior to ADR-031:
- `psl-agy-harness` enforced artifact planning (ADR-012) as a prompt convention, but `anti_drift_hook.py` did not hook directly into native Plan Mode (`mode: "plan"`) to halt premature file mutations at the PreToolUse layer.
- Our specialist catalog lacked the fuzzer/oracle capability bundle inspired by `/boost`'s adversarial verifier persona.
- Our telemetry laboratory (`telemetry.db`) did not classify native slash commands (`/boost`, `/plan`) in user intervention traces.

---

## Architectural Decisions

```mermaid
flowchart TD
    subgraph Antigravity Core Runtime
        PLAN["/plan (Plan Mode)<br/>• Shift+Tab cycle<br/>• PrependSlashPlanIfNeeded<br/>• RequestFeedback stop hook<br/>• implementation_plan.md"]
        BOOST["/boost (Deep Swarm)<br/>• Boost Multi-Agent Orchestrator<br/>• Stigmergic Blackboard File<br/>• Adversarial Verifier (Oracles)<br/>• High-Reliability Reviewer<br/>• Synthesizer Consolidation"]
    end

    subgraph PSL Harness Integrations (ADR-031)
        ADR012["PreToolUse Plan Lock (ADR-031)<br/>• Zero-write enforcement<br/>• Walkthrough artifact lifecycle"]
        LADDER["6-Stage Subagent Ladder<br/>• Deterministic ladder vs. Swarm<br/>• Custodian HEAD commit gate"]
        VERIFIER["Adversarial Verifier Bundle<br/>• Oracles, fuzzers, test generators<br/>• Scoped execute & isolated write"]
        TELEMETRY["Telemetry Laboratory<br/>• Ingest Boost traces into telemetry.db<br/>• Classify native slash commands"]
    end

    PLAN --> ADR012
    BOOST --> LADDER
    BOOST --> VERIFIER
    BOOST --> TELEMETRY
```

### 1. The Native Plan-Mode Lock Invariant
- **Decision**: The PreToolUse Anti-Drift Guard (`anti_drift_hook.py`) must treat any active `/plan` session (`mode: "plan"` or `agent_mode: "plan"`) or unapproved `implementation_plan.md` (where `RequestFeedback: true` has not yet received an explicit user confirmation) as a **zero-mutation boundary**.
- **Implementation**: Implemented `check_plan_mode_lock(payload)` in `harness/hooks/anti_drift_hook.py`. Any call to `write_to_file`, `replace_file_content`, or `edit_file` targeting non-exempt production code is deterministically denied with exit code 2 and a descriptive invariant violation notice:
  ```
  PSL Native Plan-Mode Lock (ADR-031): Session is in Plan Mode (/plan). Code modifications are locked until plan approval.
  ```
- **Exemptions**: Planning artifacts (`implementation_plan.md`, `walkthrough.md`), documentation (`.md`, `.txt`), and scratch files (`scratch/*`, `tmp/*`) remain writable via `is_exempt_file()`.

### 2. Dual Orchestration Taxonomy: Native Swarm vs. Deterministic Ladder
- **Decision**: Formally bifurcate task routing between **Native `/boost` Swarm** and the **PSL 6-Stage Subagent Ladder**:

| Dimension | Native `/boost` Swarm | PSL 6-Stage Subagent Ladder | Native `/plan` Mode | PSL ADR-012 Invariant |
| :--- | :--- | :--- | :--- | :--- |
| **Orchestration Model** | Dynamic Stigmergic Swarm | Deterministic Linear Pipeline | Modal Single Agent | Interactive Artifact Protocol |
| **Coordination Medium** | `.swarm_blackboard_<task>.md` | Staged Worktrees & State Dir | Single Prompt Prepend | `implementation_plan.md` |
| **Worker Roles** | Coder, Adversarial Verifier, Reviewer | Planner, Builder, Reviewer, Custodian, Auditor | Single Persona | Lead Architect & Specialists |
| **Commit Gate** | Synthesizer merges candidate diffs | Stage 4 Custodian atomic commit on HEAD | None | Retroactive Horizon Compaction |
| **Context Cliff Guard** | 16-Spawn Succession Protocol | Fresh context per ladder stage (<50k tokens) | Read-only planning turn | Aperture Compaction in Ledger |
| **Adversarial Verification**| Internal test generators & oracles | Sub-second benchmark & doctor audit | None | `python3 -m harness.cli test` |
| **Execution Cost** | High (Multi-agent fanout; paid plan) | Optimized (`Model: inherit`, targeted stages) | Low (Single turn) | Sub-second, zero-token overhead |

#### Operational Routing Guidelines
1. **Always Use `/plan` (or `/plan /grill-me`)**: At the start of any multi-file task to establish operator feedback loops and freeze the scope before execution.
2. **Select Native `/boost` Swarm**: For non-linear, exploratory, high-concurrency debugging, algorithmic optimization, or mysterious data races where synthetic test generators and oracles are needed to break model self-certification.
3. **Select PSL 6-Stage Subagent Ladder**: For deterministic production feature delivery, multi-module refactoring, and harness maintenance where strict stage boundaries, immutable Stage 4 Custodian Git commit gates on HEAD, and Stage 5 clean-room verification (<1.0s) are mandatory.

### 3. Adversarial Verifier Capability Bundle
- **Decision**: Codify a new verified capability bundle `adversarial_verifier` in `harness/subagents.py`:
  - **Tools**: `view_file`, `list_dir`, `grep_search`, `find_by_name`, `read_url_content`, `search_web`, `run_command`, `manage_task`, `write_to_file`, `replace_file_content`.
  - **Permissions**: `read: true`, `write: true`, `execute: true`, `subagents: false`.
  - **Purpose**: Authoring dynamic test oracles, generative fuzzers, and stress benchmarks inspired by the `/boost` verifier persona, scoped to isolated test directories without granting full orchestrator subagent powers.

### 4. Telemetry Classification for Native Slash Commands
- **Decision**: Extend `pipeline/extract_transcripts.py` and `harness/telemetry/sync.py` to identify and record native slash commands in `telemetry.db`:
  - `BOOST_ORCHESTRATION`: Sessions or turns initiated with `/boost`.
  - `PLAN_INITIATION`: Turns initiated with `/plan`.
  - `CONFIRMATION`: User interventions that approve plans (`proceed`, `approved`, `lgtm`, `approved this document`).

---

## Consequences

### Positive
- **Deterministic Plan Safety**: Premature code mutations during `/plan` mode are halted at the PreToolUse hook layer, eliminating speculative edits before operator sign-off.
- **Clean Taxonomy**: Developers and subagents have unambiguous criteria for choosing between Native `/boost` Swarms and the PSL 6-Stage Subagent Ladder.
- **Dedicated Test Oracles**: The `adversarial_verifier` capability bundle allows authoring property tests, generators, and stress tests inspired by `/boost`.
- **Empirical Telemetry Insights**: Telemetry sync classifies native slash command usage (`/boost`, `/plan`) to evaluate real-world developer steering patterns.

### Negative / Tradeoffs
- **Mode Strictness**: Developers testing trivial experimental edits in `/plan` mode must either switch modes (`Shift+Tab`) or click "Proceed" before code files can be written.
- **Dual Orchestration Awareness**: Agents and operators must understand the distinct operational boundaries between probabilistic swarms (`/boost`) and deterministic linear pipelines (Subagent Ladder).

---

## Verification & Testing Contracts

1. **Plan-Mode Lock Hermetic Tests**:
   - `TestAntiDriftHook.test_plan_mode_blocks_code_mutations`: Asserts that `write_to_file` on code files is denied with exit code 2 when `mode: "plan"`.
   - `TestAntiDriftHook.test_plan_mode_allows_exempt_files`: Asserts that `implementation_plan.md`, documentation, and scratch paths remain editable during plan mode.
   - `TestAntiDriftHook.test_plan_mode_inactive_allows_flow`: Asserts that non-plan modes operate normally without blocks.
2. **Capability Bundle Test**:
   - `TestAgentScaffoldAndValidation.test_capability_bundles_use_platform_tools`: Asserts that `adversarial_verifier` contains only verified platform tools.
3. **Sub-Second Benchmark Invariant**:
   - The entire test suite executes in **<1.0s** benchmark target across all unit and contract tests.
