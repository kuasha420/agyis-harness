# 🗺️ PSL Harness: Master Product Vision, Contracts & Roadmap
**Project**: PSL Harness for Google Antigravity™ (`psl-agy-harness`)  
**Publisher**: Purrfect Software Limited (PSL)  
**License**: Apache-2.0  
**Repository**: `kuasha420/psl-agy-harness` (Private Development → Public Release)  
**Last Updated**: 2026-10-03  

---

## 1. The North Star & Product Vision

### The Fundamental Motivation
We rely heavily on Google's modern Gemini models—with **Gemini 3.8 Flash** as our primary high-throughput SWE workhorse and **Gemini 3.1 Pro** as our deep architectural reasoning model—for their market-leading reasoning aperture, rapid tool dispatch, massive context windows, and price-to-performance ratio in software engineering automation. However, developer productivity in long-horizon coding tasks is frequently constrained by harness-level friction:
- **Context Cliffs**: Unpruned tool outputs dump thousands of lines into context, accelerating the 100k-token cognitive degradation cliff.
- **Brittle Terminal Desyncs**: 98.4% of all tool failures occur in `run_command`, driven by benign exit code 1 panics, pyenv/conda shim hijacking, and interactive subshell hangs.
- **Premature Convergence & Cognitive Drift**: In deep sessions, models succumb to "chatbot seduction", confusing speculative text proposals with working code, rationalizing incomplete work, and perseverating on repetitive thought mantras.
- **Rigid Single-Threaded Loops**: Lack of hardware mesh and fleet awareness.

### The Product Definition
Rather than creating an isolated competing framework that reinvents agent execution from scratch, **`psl-agy-harness` is a dual-purpose system**:
1. **The Empirical Laboratory**: Automated telemetry mining tools that extract mathematical ground truth from thousands of real developer trajectories, loop patterns, and failure modes.
2. **The Reference Extension Harness**: A high-performance, deterministic extension harness built *strictly on official Google Antigravity surfaces* (`plugin.json`, lifecycle hooks, MCP, rules) that solves environment and context bottlenecks deterministically in code, ensuring high autonomy and reliability for local and distributed agent execution.

### The Victory Playbook: Reinforcing What Worked Across 348 Sessions
The mission of PAH is not merely defensive error mitigation; it is **actively codifying and amplifying the battle-tested patterns that produced near-zero error and intervention rates** across our empirical dataset:

1. **Subagent Ladder & Worktree Sharding (`Executioner -> Hammer -> Auditor`)**:
   - `invoke_subagent` and `manage_subagents` achieved a **99.5% success rate** across 215 calls in the telemetry database.
   - Spawning isolated subagents in worktrees for multi-phase tasks (test suites, refactors, lint passes) protects the coordinator's attention aperture, preventing the primary context window from crossing the 50k token cliff.
2. **Explicit Command Dictionaries (The Golden Monorepo Pattern)**:
   - Workspaces declaring exact, copy-pasteable CLI invocations (`purrmission` with **1.67 interventions/session**, `sunshine-physio` with **1.91**) experienced **10x lower human interventions** than workspaces with multi-file rule indirection (`mm-website` with **18.2**).
   - The harness product must automatically inject verified project script palettes (`package.json`, `pyproject.toml`) so agents never guess command invocations or monorepo filters.
3. **Delta-Focused Code Review Cycles**:
   - High-performing trajectories rely on structured PR review delay fences (e.g. `node scripts/gh-pr-review-comments.cjs`) and incremental delta resolution rather than full-repository diff re-reads, allowing CI checks to settle before fixes are attempted.
4. **Surgical Contiguous Edits**:
   - `replace_file_content` achieved a **99.9% tool success rate** (only 4 failures out of 4,650 calls).
   - High-fidelity sessions enforce single contiguous block modifications rather than destructive whole-file rewrites.
5. **Knot Physical Mesh Specialization**:
   - Multi-node hardware strand specialization (Desktop Anchor Architect, Laptop CUDA Compute Worker, Handheld Controllers on Steam Deck and ROG Ally) succeeds when bound to strict role profiles, network timeouts (`-o ConnectTimeout=5`), and zero-sudo user-space toolchains (`uv`).

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

### C. The Product vs. Project Bifurcation (ADR-014)
A critical architectural boundary separates the runtime software delivered to agents from the internal development workspace:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   THE PRODUCT (psl-agy-harness runtime)                │
│ Distributable Antigravity plugin and developer CLI toolchain:           │
│ - Runtime Matrix (matrix.json) & Auto-Healing Doctor                   │
│ - Deterministic Lifecycle Hooks (hooks.json, command safety, anti-loop) │
│ - Unified CLI Entrypoint (`psl doctor`, `psl hook`, `psl audit`)        │
│ - Product-Level Rules & Skills (AGENTS.md, testing contracts, toolkit) │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ engineered & audited by
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   THE PROJECT (Development & Empirical Lab)            │
│ Local repository workspace (kuasha420/psl-agy-harness):               │
│ - Telemetry Database (data/telemetry.db: 348 sessions, 140k steps)     │
│ - Analysis Pipelines (pipeline/extract_*.py, analyze_*.py)             │
│ - Project Test Suite (tests/: hermetic unit & contract tests)          │
│ - Architecture Specifications & Research Ledgers (docs/taxonomy/)      │
└────────────────────────────────────────────────────────────────────────┘
```

1. **The Product**: Ships to developers and agent strands across workspaces. Contains zero developer-specific telemetry scripts or scratch files.
2. **The Project**: The engineering repository where PAH is developed, containing the 348-session database, multi-dimensional taxonomy reports, and internal verification suites.

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

### 🟢 Horizon 0: Empirical Ground Truth & POC Prototyping (COMPLETED & COMPACTED)
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

### 🟡 Horizon 1: Product Foundation, Delivery Architecture & Packaging (IN PROGRESS)
* **Goal**: Move from isolated scripts to a unified developer product; codify testing contracts; build the delivery engine; harvest deeper telemetry.
* **Resolution**: **Medium Resolution (Macro Milestones & Architectural Boundaries)**.
* **Completed Milestones**:
  - [x] **Unified Developer CLI (`psl`)**:
    - Created `harness/cli.py` providing `psl doctor`, `psl hook`, `psl test`, `psl audit`, and `psl status`.
    - Registered `psl` in `pyproject.toml` and `package.json`.
    - Standardized `hooks.json` to invoke `python3 -m harness.cli hook <name>`, eliminating relative path bugs.
  - [x] **Testing Codification & Anti-Loop Test Suite**:
    - Refactored `anti_loop_hook.py` with pure `check_anti_loop()` and dynamic `PSL_HARNESS_STATE_DIR` support.
    - Added `tests/test_anti_loop.py` (7 tests) and `tests/test_cli.py` (7 tests).
    - Codified `docs/official-specs/testing-contracts.md` (Tier 1 Project Contracts & Tier 2 Product Blueprint).
    - Entire test suite passes with **43/43 tests in <0.85s** (Sub-second benchmark invariant met).
  - [x] **Modular Product Skills & Specialist Agent Scaffold (Phase 5.2)**:
    - Codified 5 modular stack skills (`psl-stack-shell`, `psl-stack-typescript`, `psl-stack-python`, `psl-stack-backend`, `psl-stack-systems`) with frontmatter parser and sync engine.
    - Codified 3 specialist subagent archetypes (`harness_builder`, `harness_reviewer`, `harness_auditor`) with toolgroup permissions and programmatic registry (`harness/subagents.py`).
    - Added CLI discovery subcommands (`psl skills`, `psl agents`) and updated `psl status`.
    - Added hermetic test suites (`tests/test_skills.py`, `tests/test_subagents.py`), passing 61/61 tests in 0.904s (<1.0s benchmark invariant).
    - Executed end-to-end via the **Subagent Ladder** protocol (`Executioner` -> `Hammer` -> `Auditor`).
  - [x] **Telemetry Data Gathering & Deep Mining (Phase 1)**:
    - Enriched `tool_calls` schema non-destructively with `output_length_chars`, `output_lines`, `arguments_length_chars`, `command_category`, and `is_truncated`.
    - Backfilled 64,402 tool calls across 347 sessions in `data/telemetry.db`.
    - Created `pipeline/analyze_volume_distributions.py` and CLI command `psl audit volume`.
    - Proved 2KB compactor eliminates **35,754,488 characters (~8,938,622 tokens)**, achieving **35.75% volume reduction** with **0 ADR-008 failure preservation violations**.
    - Produced canonical report `docs/taxonomy/tool-volume-distribution-report.md` and machine-readable data `data/volume_distributions.json`.
    - Complete test suite passes: 67/67 tests in 0.932s (<1.0s benchmark).
  - [x] **Ultra-Deep Horizon Microscope & Knot Autopsy (Phase 0.5)**:
    - Dissected all 30 titan sessions ($\ge 1,000$ steps) representing 84,755 steps (60% of total workstation history).
    - Identified 3 empirical survival archetypes: Type A Survivors, Type B Systems Breakthroughs, and Type C Thrashing Traps.
    - Conducted forensic timeline autopsy of Knot genesis session (`8cbe936a`, 3,357 steps).
    - Produced canonical report `docs/taxonomy/ultra-deep-sessions-survival-report.md` and CLI integration `./psl audit deep`.
  - [x] **Deterministic Stop-Hook Verification Fence (ADR-022 Phase 1)**:
    - Implemented `completion_fence_hook.py` intercepting code file edits (`write_to_file`, `replace_file_content`, `edit_file`) in `PreToolUse` and blocking premature exits in `Stop`.
    - Integrated multi-session dirty clearance in `./psl test` and 2-block anti-deadlock safety valve.
  - [x] **Terminal Execution & Subshell PATH Reliability (ADR-023 Phase 2)**:
    - Implemented `get_user_path_shims()`, `inject_path_shims()`, and `inject_ssh_timeouts()` in `command_safety_hook.py`.
    - Eliminated non-login subshell Exit 127 for modern toolchains (`uv`, `pnpm`, `cargo`, `pytest`) and resolved indefinite SSH hangs with non-blocking timeouts (`-o ConnectTimeout=5`).
  - [x] **Plan-to-Execution Anti-Drift & Cognitive Anchors (ADR-024 Phase 3)**:
    - Implemented `anti_drift_hook.py` with multi-syntax boundary parser, non-code exemptions (`.md`, `.txt`, artifacts, scratch), and dual-mode gating (non-strict notices vs strict `ask` confirmation gates).
    - Integrated Cognitive Attention Horizon Gauge into `psl status` across Healthy, Amber, and Red Alert depth zones.
  - [x] **Subagent Lifecycle Ergonomics, Zero-Token Context Gauge & Execution Reliability (ADR-025 Phase 4)**:
    - Implemented `SubagentContextStatus`, zero-token context estimator (`estimate_subagent_context`), and high-performance directory scanner (`list_active_subagent_statuses`) in `harness/subagents.py`.
    - Wired PreToolUse Auditor Write-Block Guard (`check_auditor_write_block`) in `harness/hooks/anti_drift_hook.py`, enforcing verification-only safety for `harness_auditor` without disabling `run_command` or reading tools.
    - Updated agent archetypes (`harness_auditor`, `harness_builder`, `harness_reviewer`) with Zero-Exploration Invariants and synced `.agents/agents/`.
    - Added `psl subagents` subcommand (`--json`, `--brain-dir`) and wired live active subagent health gauges into `psl status`.
    - Expanded test suite to **135 hermetic unit/contract tests passing in <0.92s** (<1.0s benchmark invariant).
  - [x] **Custom Codebase & Workspace-Aware Agents (ADR-026 Phase 5)**:
    - Expanded specialist catalog to 5 personas (`planner`, `coordinator`, `harness_builder`, `harness_reviewer`, `harness_auditor`) with `mainAgent: true` surfacing in the Antigravity chat UI.
    - Implemented registry, capability bundles (`read_only`, `verifier`, `builder`, `orchestrator`), automated workspace inspection, and specification validator in `harness/subagents.py`.
    - Added `agents create`, `agents validate`, and `agents --sync` CLI subcommands.
    - Authored modular `agent-builder` skill with automated scanning and validation gates.
    - Expanded write-block protection across `planner`, `coordinator`, `auditor`, and `reviewer` in `anti_drift_hook.py`.
    - Expanded test suite to **149 hermetic tests passing in 0.968s** (<1.0s benchmark invariant).
* **Upcoming Milestones**:
  1. **The Rule/Skill Delivery & Coexistence Engine**:
     - Implement Layer 1 vs Layer 3 resolution engine.
     - Provide `psl install [--global]` to register the plugin into `~/.gemini/config/plugins/` without polluting workspace git repositories.
  2. **Standardized Testing Runner Skills**:
     - Supply standardized testing runner skills (`psl-test-runner`) for Python, Node, Cargo, and Go.
  3. **In-Band PreToolUse Execution Compactor**:
     - Evaluate tuning and live wrapper prototypes based on the codified 2KB sweet spot.

---

### ⚪ Horizon 2: Fleet Scaling & Knot Hardware Mesh (FUTURE)
* **Goal**: Expand from single-workstation optimization to distributed cluster execution across the physical Knot mesh.
* **Resolution**: **Low Resolution (Strategic Vision)**.
* **Key Milestones**:
  - Remote strand telemetry routing (`laptop`, `rog-ally`, `steamdeck`).
  - Out-of-band multi-agent coordination via Linda Tuplespace and GitHub Discussions (`swarm-council`).
  - Decoupled visual cockpits on worker displays.

