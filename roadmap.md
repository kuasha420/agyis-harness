# 🗺️ PSL Harness: Master Product Vision, Contracts & Roadmap
**Project**: PSL Harness for Google Antigravity™ (`psl-agy-harness`)  
**Publisher**: Purrfect Software Limited (PSL)  
**License**: Apache-2.0  
**Repository**: `kuasha420/psl-agy-harness` (Private Development → Public Release)  
**Last Updated**: 2026-10-02  

---

## 1. The North Star & Product Vision

### The Fundamental Motivation
We rely heavily on Google's models (Gemini 1.5 Pro/Flash, Gemini 2.0) for their market-leading reasoning, massive context windows, and price-to-performance ratio in SWE automation. However, the model is frequently throttled by official harness limitations:
- **Context Cliffs**: Unpruned tool outputs dump thousands of lines into context, accelerating the 100k-token cognitive degradation cliff.
- **Brittle Terminal Desyncs**: 98.4% of all tool failures occur in `run_command`, driven by benign exit code 1 panics, pyenv/conda shim hijacking, and interactive subshell hangs.
- **Premature Convergence & Cognitive Drift**: In deep sessions, models succumb to "chatbot seduction", confusing speculative text proposals with working code, rationalizing incomplete work, and perseverating on repetitive thought mantras.
- **Rigid Single-Threaded Loops**: Lack of hardware mesh and fleet awareness.

### The Product Definition
Rather than creating an isolated competing framework that reinvents agent execution from scratch, **`psl-agy-harness` is a dual-purpose system**:
1. **The Empirical Laboratory**: Automated telemetry mining tools that extract mathematical ground truth from thousands of real developer trajectories, loop patterns, and failure modes.
2. **The Reference Extension Harness**: A high-performance, deterministic extension harness built *strictly on official Google Antigravity surfaces* (`plugin.json`, lifecycle hooks, MCP, rules) that solves environment and context bottlenecks deterministically in code—so our patterns can either be used directly by developers or **upstreamed directly to Google DeepMind**.

---

## 2. Core Architectural Contracts

### A. The Separation Invariant: "Code Enforces, Prompts Guide Cognition"
* **Deterministic problems belong in software hooks, NOT prompt rules**:
  - Runtime environment selection (`PATH` injection, Python 3.12 PEP 701 support) is handled by `PreToolUse` hooks and `psl doctor`.
  - Terminal exit-code sanitization (surgical `|| [ $? -eq 1 ]`) is handled by `command_safety_hook.py`.
  - Non-interactive pager enforcement (`PAGER=cat`) is injected automatically.
  - Context volume suppression is handled by output compaction hooks.
* **Agent rules (`AGENTS.md`) are reserved strictly for cognitive invariants** that software cannot deterministically enforce (anti-loop heuristics, context flood piping, artifact-first planning, human confirmation gates).

### B. The Rule & Skill Delivery & Coexistence Contract (Unresolved Core Challenge)
A central unsolved architectural challenge of this product is **how the harness delivers runtime rules and skills without colliding with or overwriting project-specific customizations**:

```
┌────────────────────────────────────────────────────────────────────────┐
│ Layer 3: Project / Workspace (.agents/rules/, .agents/skills/)         │
│ Highest precedence. Domain-specific business logic & repository rules.  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Layer 2: User Environment (~/.gemini/antigravity/rules/, skills/)      │
│ Operator-specific developer preferences across all workspaces.          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Layer 1: PSL Harness Plugin (plugin.json, hooks, psl-audit-toolkit)    │
│ Deterministic lifecycle hooks, baseline runtime matrix, safety fences. │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Layer 0: Native Antigravity Platform Defaults                          │
│ Base models, standard tool definitions, platform execution runtime.    │
└────────────────────────────────────────────────────────────────────────┘
```

#### Key Coexistence Rules:
1. **Zero Git Pollution**: Harness-provided rules and skills must never be forcefully copied into a target repository's `.agents/` folder unless explicitly scaffolded by the operator.
2. **Deterministic Precedence**: Project-local skills and rules always specialize or override harness-level skills of the same name.
3. **Non-Destructive Cascading**: Harness hooks operate globally at the platform layer, providing safety and compaction across all repositories without requiring repo-specific setup.

---

## 3. Cognitive Exhaustion Guardrails & Visual Indicators

Our empirical audit proved that session depth is the single greatest catalyst of cognitive failure:
- Trajectories `<50` steps / `<50k` tokens maintain near-zero error and intervention rates (0.8 errors/session).
- Trajectories `>200` steps / `>100k` tokens experience a **20x error spike** and **40x intervention spike**, culminating in **Attention Sink Collapse** (where models perseverate on identical thought loops 85.5% of the time) and **Premature Convergence** (declaring prototypes "complete").

### The Visual Cockpit & Guardrail Architecture

To protect both the operator and the agent from cognitive exhaustion, the harness introduces three guardrails:

```
┌────────────────────────────────────────────────────────────────────────┐
│                      CONTEXT DEPTH COCKPIT GAUGE                       │
│                                                                        │
│  [■■■■■■■■■■■■■■■■■■■■░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 35k Tokens │
│  STATUS: 🟢 HEALTHY (High Attention Aperture | Exact Reasoning)         │
└────────────────────────────────────────────────────────────────────────┘
```

1. **Visual Depth Gauges (GUI / Terminal Header)**:
   - 🟢 **Healthy Zone (`<50k` tokens / `<50` steps)**: High attention resolution, reliable reasoning.
   - 🟡 **Amber Warning (`50k–100k` tokens / `50–100` steps)**: Attention stretching; compaction recommended.
   - 🔴 **Red Alert (`>100k` tokens / `>100` steps)**: Context cliff active. High risk of premature convergence, loop repetition, and speculative plan dumping.
2. **Hard Horizon Compaction Fence**:
   - When a milestone completes or token depth enters the Red Alert zone, execution halts.
   - The coordinator must compact findings into `docs/taxonomy/project-ledger.md` under 50 lines, update `roadmap.md`, commit clean code to git, and **instruct the operator to reset into a fresh session**.
3. **The Artifact-First Planning Invariant (ADR-012)**:
   - Prohibits proposing multi-component architecture in raw conversational chat turns ("Chatbot Seduction").
   - All non-trivial proposals must immediately crystallize into an interactive `implementation_plan.md` artifact before requesting approval.

---

## 4. Master Roadmap Horizons (Dynamic Sliding Aperture)

### 🟢 Horizon 0: Empirical Ground Truth & POC Prototyping (CURRENT — LOCKED IN)
* **Goal**: Replace intuition with empirical telemetry; dissect platform interfaces; build isolated proof-of-concept hooks.
* **Status**: **Complete & Compacted** (All code on `main`, tests green, ledger updated).
* **Delivered Assets**:
  - `pipeline/extract_transcripts.py` & `data/telemetry.db`: Ingested 348 sessions, 140,005 steps, 64,065 tool calls.
  - `docs/taxonomy/workstation-audit-report.md`: De-aggregated 1,544 Exit Code 1 failures (329 grep misses, 58 python syntax errors, 142 tracebacks).
  - `docs/taxonomy/cognitive-failure-taxonomy-deepdive.md`: Analyzed Repetition Trap, Exit Code 1 Panic, and Attention Sink Collapse.
  - `docs/official-specs/platform-surface-mapping.md`: 655-line deconstruction of CLI (`agy`), 2.0 Desktop Platform, Python SDK, hooks, and MCP boundaries.
  - `harness/hooks/output_compactor_hook.py`: Deterministic 2KB head/tail output compactor (13/13 tests pass).
  - `harness/runtime/matrix.json` & `pipeline/psl_doctor.py`: Telemetry-scaffolded 3-tier runtime matrix + zero-sudo auto-healing doctor (8/8 tests pass).
  - `harness/hooks/command_safety_hook.py`: PreToolUse CPython 3.12 injection, f-string sanitization, surgical grep exit-1 filter, pager normalization (8/8 tests pass).
  - `.agents/rules/AGENTS.md`: Pruned to 54 lines of pure cognitive signal.

---

### 🟡 Horizon 1: Product Foundation, Delivery Architecture & Packaging (NEXT SESSION)
* **Goal**: Move from isolated scripts to a unified developer product; solve the rule/skill delivery and coexistence problem; integrate in-band context compaction.
* **Resolution**: **Medium Resolution (Macro Milestones & Architectural Boundaries)**.
* **Key Milestones**:
  1. **Unified CLI & Manifest Packaging**:
     - Package the toolchain into a single distributable binary or Python entrypoint: `psl doctor`, `psl audit`, `psl hook`.
     - Finalize `plugin.json` for 1-command installation via `agy plugin install .`.
  2. **The Rule/Skill Delivery Engine**:
     - Formalize and implement the Layer 1 vs Layer 3 resolution engine.
     - Ensure global harness skills (audit toolkit, mesh runners) are discoverable without polluting project repositories.
  3. **In-Band PreToolUse Context Compactor**:
     - Move beyond `PostToolUse` telemetry logging: wrap execution so that large tool outputs are compacted *before* reaching the LLM context window, physically eliminating the 100k token cliff during live runs.
  4. **Context Cockpit & Visual Status Display**:
     - Implement token depth and step horizon indicators in Antigravity's auxiliary pane or terminal headers.

---

### ⚪ Horizon 2: Fleet Scaling & Knot Hardware Mesh (FUTURE)
* **Goal**: Expand from single-workstation optimization to distributed cluster execution across the physical Knot mesh.
* **Resolution**: **Low Resolution (Strategic Vision)**.
* **Key Milestones**:
  - Remote strand telemetry routing (`laptop`, `rog-ally`, `steamdeck`).
  - Out-of-band multi-agent coordination via Linda Tuplespace and GitHub Discussions (`swarm-council`).
  - Decoupled visual cockpits on worker displays.

---

### ⚪ Horizon 3: Upstream RFCs to Google DeepMind (UPSTREAM)
* **Goal**: Feed empirical data and reference implementations back into official Google Antigravity platforms.
* **Resolution**: **Low Resolution (Strategic Vision)**.
* **Key Milestones**:
  - RFC 1: Native configurable tool output compaction thresholds in `agy`.
  - RFC 2: Native `PreToolUse` environment variable / PATH injection contracts.
  - RFC 3: Deprecation of agent polling loops in favor of reactive task notification wakeups.
