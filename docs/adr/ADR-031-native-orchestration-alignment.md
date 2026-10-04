# ADR-031: Native Orchestration Alignment (Boost, Plan Mode & Agent Builder)

* **Status**: Accepted
* **Date**: 2026-10-05
* **Authors**: Antigravity & PSL Lead Architect
* **Scope**: `harness/`, `pipeline/`, `.agents/`, `docs/`

---

## Context & Motivation

Antigravity core (v1.1.0 through v1.2.16) has formalized several high-level agent primitives:
1. **`/plan` mode**: Pre-execution planning loop enforcing read-only exploration and the creation of an `implementation_plan.md` artifact with `RequestFeedback: true`.
2. **`/boost` mode**: On-demand multi-agent swarm orchestrator utilizing stigmergic blackboard coordination (`.swarm_blackboard_<task>.md`), an adversarial verifier persona (test generators + oracles), and high-reliability review workers.
3. **`/agent-builder` & Custom Agents**: Native discoverability of `.agents/agents/*.md`, inline `@<agent>` routing, and UI tool prerequisite pruning.

Prior to ADR-031, `psl-agy-harness` enforced artifact planning (ADR-012) and specialist scaffolding (ADR-026, ADR-030) as harness-level conventions without deep telemetry classification or native mode synchronization. This created potential divergences between IDE-driven slash commands and harness hook guarantees.

---

## Architectural Decisions

### 1. The Native Plan-Mode Lock Invariant
- **Decision**: The PreToolUse Anti-Drift Guard (`anti_drift_hook.py`) must treat any active `/plan` session or unapproved `implementation_plan.md` (where `RequestFeedback: true` has not yet received an explicit user confirmation) as a **zero-mutation boundary**.
- **Enforcement**: Any call to `write_to_file`, `replace_file_content`, or `edit_file` outside `<Artifact Directory>/implementation_plan.md` during a planning turn is strictly blocked with exit code 2 and a descriptive invariant violation notice.

### 2. Dual Orchestration Taxonomy: Swarm vs. Deterministic Ladder
- **Decision**: Formally bifurcate task routing between **Native `/boost`** and the **PSL 6-Stage Subagent Ladder**:
  - **Native `/boost` Swarm**: Recommended for non-linear, exploratory, high-concurrency debugging or deep algorithmic optimization where synthetic test generators and oracles are needed to break model self-certification.
  - **PSL 6-Stage Subagent Ladder**: Mandatory for production feature delivery, multi-module refactoring, and harness maintenance where strict stage boundaries, immutable Stage 4 Custodian Git commit gates on HEAD, and Stage 5 sub-second clean-room verification are non-negotiable.

### 3. Adversarial Verifier Capability Bundle
- **Decision**: Add a new verified capability bundle `adversarial_verifier` to `ANTIGRAVITY_PLATFORM_TOOLS` in `harness/subagents.py`:
  - **Tools**: `view_file`, `list_dir`, `grep_search`, `find_by_name`, `run_command`, `manage_task`, `write_to_file`, `replace_file_content` (scoped to isolated temporary test directories or test files).
  - **Purpose**: Authoring dynamic test oracles, generative fuzzers, and stress benchmarks inspired by the `/boost` verifier persona.

### 4. Telemetry Telemetry Classification for Native Slash Commands
- **Decision**: Extend `pipeline/extract_transcripts.py` and `harness/telemetry/sync.py` to identify and record:
  - `BOOST_ORCHESTRATION`: Sessions initiated with or containing `/boost`.
  - `PLAN_INITIATION`: Turns initiated with `/plan`.
  - `AGENT_BUILDER_INVOCATION`: Turns invoking the `/agent-builder` skill.
  - `PLAN_CONFIRMATION`: User interventions that approve plans (`proceed`, `approved`, `lgtm`).

---

## Consequences

### Positive
- Direct platform alignment: Harness rules seamlessly harmonize with Antigravity's IDE feedback banners, `Shift+Tab` mode cycling, and `@<agent>` autocomplete.
- Zero premature mutations: Even if an agent attempts speculative code edits during a `/plan` turn, `anti_drift_hook.py` halts the mutation at the PreToolUse layer.
- Empirical visibility: Telemetry laboratory can measure whether `/boost` or Subagent Ladder yields higher first-pass verification rates on specific problem classes.

### Negative / Tradeoffs
- Strictness: Developers testing quick changes in `/plan` mode must either switch modes (`Shift+Tab`) or click "Proceed" before code can be written.
