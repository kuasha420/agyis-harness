<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# 🗺️ PSL Harness: Master Product Vision, Contracts & Roadmap
**Project**: Agyis Harness for Google Antigravity™ (`agyis-harness`)  
**Publisher**: Purrfect Software Limited (PSL)  
**License**: Apache-2.0  
**Repository**: `kuasha420/agyis-harness` (Private Development → Public Release)  
**Last Updated**: 2026-10-18  

---

## 1. The North Star & Product Vision

### The Fundamental Motivation
We rely heavily on Google's modern Gemini models—with **Gemini 3.8 Flash** as our primary high-throughput SWE workhorse and **Gemini 3.1 Pro** as our deep architectural reasoning model—for their market-leading reasoning aperture, rapid tool dispatch, massive context windows, and price-to-performance ratio in software engineering automation. However, developer productivity in long-horizon coding tasks is frequently constrained by harness-level friction:
- **Context Cliffs**: Unpruned tool outputs dump thousands of lines into context, accelerating the 100k-token cognitive degradation cliff.
- **Brittle Terminal Desyncs**: 98.4% of all tool failures occur in `run_command`, driven by benign exit code 1 panics, pyenv/conda shim hijacking, and interactive subshell hangs.
- **Premature Convergence & Cognitive Drift**: In deep sessions, models succumb to "chatbot seduction", confusing speculative text proposals with working code, rationalizing incomplete work, and perseverating on repetitive thought mantras.
- **Rigid Single-Threaded Loops**: Lack of hardware mesh and fleet awareness.

### The Product Definition
Rather than creating an isolated competing framework that reinvents agent execution from scratch, **`agyis-harness` is a dual-purpose system**:
1. **The Empirical Laboratory**: Automated telemetry mining tools that extract mathematical ground truth from thousands of real developer trajectories, loop patterns, and failure modes.
2. **The Reference Extension Harness**: A high-performance, deterministic extension harness built *strictly on official Google Antigravity surfaces* (`plugin.json`, lifecycle hooks, MCP, rules) that solves environment and context bottlenecks deterministically in code, ensuring high autonomy and reliability for local and distributed agent execution.

### The Victory Playbook: Reinforcing What Worked Across 348 Sessions
The mission of PAH is not merely defensive error mitigation; it is **actively codifying and amplifying the battle-tested patterns that produced near-zero error and intervention rates** across our empirical dataset:

1. **Subagent Ladder & Worktree Sharding (`Executioner -> Hammer -> Custodian -> Auditor`)**:
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
  - Runtime environment selection (`PATH` injection, Python 3.12 PEP 701 support) is handled by `PreToolUse` hooks and `agyis doctor`.
  - Terminal exit-code sanitization (surgical `|| [ $? -eq 1 ]`) is handled by `command_safety_hook.py`.
  - Non-interactive pager enforcement (`PAGER=cat`) is injected automatically.
  - Context volume suppression is handled by output compaction hooks.
* **Agent rules (`AGENTS.md`) are reserved strictly for cognitive invariants** that software cannot deterministically enforce (anti-loop heuristics, context flood piping, artifact-first planning, human confirmation gates).

### B. The Rule & Skill Delivery & Coexistence Contract
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
```
┌────────────────────────────────────────────────────────────────────────┐
│                   THE PRODUCT (agyis-harness runtime)                  │
│ Distributable Antigravity plugin and developer CLI toolchain:           │
│ - Runtime Matrix (matrix.json) & Auto-Healing Doctor                   │
│ - Deterministic Lifecycle Hooks (hooks.json, command safety, anti-loop) │
│ - Unified CLI Entrypoint (`agyis doctor`, `agyis hook`, `agyis audit`)  │
│ - Product-Level Rules & Skills (AGENTS.md, testing contracts, toolkit) │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ engineered & audited by
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   THE PROJECT (Development & Empirical Lab)            │
│ Local repository workspace (kuasha420/agyis-harness):               │
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

### 🟢 Horizon 1: Product Foundation, Delivery Architecture & Packaging (COMPLETED & COMPACTED)
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
  - [x] **Remote Agentic Execution, SSH Multiplexing & Cloud/Mesh Troubleshooting Harness (ADR-027 Phase 7)**:
    - Dissected 3,257 SSH calls across 37 sessions, uncovering the 7 primary friction vectors of remote execution.
    - Upgraded `command_safety_hook.py` with transparent OpenSSH ControlMaster multiplexing (`~/.cache/psl/ssh/cm_%C`), dropping latency from ~2,000ms to <50ms.
    - Implemented remote ADR-013 pattern probe sanitization (`|| [ \$? -eq 1 ]`) inside SSH payloads, neutralizing false-positive Exit 1 failures on remote grep/diff.
    - Implemented selective login-shell wrapping (`bash -l -c '...'`) for toolchains (`node`, `pm2`, `pnpm`, `cargo`, `nvm`, `uv`), eliminating the non-login Exit 127 trap.
    - Built unified `harness/remote/` subsystem with `RemoteRunner`, zero-residue `ScriptStreamer` (stdin streaming), and compact `<2KB` `RemoteTriage`.
    - Added `psl remote` CLI palette (`exec`, `script`, `triage`, `socket`).
    - Codified modular skill `remote-ops` and updated `psl-stack-shell` with Remote Invariants.
    - Expanded hermetic test suite to **180 tests passing in 0.933s** (<1.0s benchmark invariant).
  - [x] **Agent Tooling Realignment & Client-Side Redaction Engine (ADR-030 Phases 1 & 2)**:
    - Resolved agent permissions paradox by enabling write/subagent/question tooling for `planner` and `coordinator`, delegating fine-grained safety boundaries to `anti_drift_hook.py`.
    - Implemented zero-dependency client-side telemetry redaction engine (`harness/telemetry/redaction.py`) scrubbing secrets, credentials, and private filesystem paths.
    - Added comprehensive hermetic test suite (`tests/test_redaction.py`), expanding suite to 208 passing tests.
  - [x] **Global Plugin Delivery, Coexistence Engine & 6-Stage Subagent Ladder (ADR-030 Phase 6)**:
    - Implemented `PluginInstaller` in `harness/delivery.py` supporting global installations to `~/.gemini/config/plugins/` with path safety guards.
    - Codified Three-Tier Precedence Hierarchy: Layer 3 (Workspace Local `.agents/`) > Layer 2 (User Preferences `~/.gemini/antigravity/`) > Layer 1 (Global Plugin).
    - Standardized 6-Stage Subagent Ladder with Stage 4 Custodian Commit Gate to guarantee immutable git revisions before verification.
    - Cataloged 7 specialist subagents and expanded test suite to 237 tests.
  - [x] **Centralized Telemetry Gateway, GitHub Org Auth & Client Transport (ADR-030 Final Closure)**:
    - Implemented in-tree Starlette gateway (`server/`) with dual-engine storage (PostgreSQL in production/Docker, in-memory SQLite for tests).
    - Delivered GitHub Org authentication (`purrfectsoft` default / `PSL_GITHUB_ORG`) with in-memory token cache (TTL 300s).
    - Implemented idempotent session upserts (`ON CONFLICT DO UPDATE`) and anti-echo delta replication (`origin_developer != requesting_user`).
    - Built zero-dependency client transport in `harness/telemetry/sync.py` (`urllib.request` only) with mandatory pre-serialization secret scrubbing.
    - Delivered `psl auth login|status|logout` and upgraded `psl sync` bi-directional CLI.
    - Generated containerization and CloudPanel loopback deployment profiles (`server/deploy.sh`, `docker-compose.yml`, systemd unit).
    - Expanded hermetic test suite to **256 passing tests in 1.289s**.
  - [x] **Native Orchestration Alignment: Boost Swarm & Plan Mode (ADR-031 Phase 8)**:
    - Reverse-engineered Antigravity internal Go binary implementations of native `/boost` and `/plan`.
    - Formulated and finalized ADR-031 and authored complete research specification (`docs/official-specs/antigravity-boost-and-plan.md`).
    - Implemented PreToolUse Native Plan-Mode Lock (`check_plan_mode_lock`) in `harness/hooks/anti_drift_hook.py`.
    - Codified `adversarial_verifier` capability bundle in `harness/subagents.py` for test generators and stress oracles.
    - Extended transcript extraction in `pipeline/extract_transcripts.py` to classify native slash commands (`BOOST_ORCHESTRATION`, `PLAN_INITIATION`).
    - Decoupled custom agent scaffolding (`agent-builder`) to remain solely anchored in ADR-026.
    - Expanded hermetic test suite to **259 passing tests in 1.297s** (with 47 anti-drift & scaffold tests in 0.028s).
  - [x] **Production Hardening: Chunked Telemetry Push, Zero-PWD Resolution & Global Delivery (Phase 9 - ADR-030)**:
    - Enforced zero-PWD DB path resolution hierarchy; client-side chunked telemetry push (10 sessions / 2,500 steps) mitigating HTTP 413.
    - Delivered standalone global executable `~/.local/bin/psl` (`0o755`) via `PluginInstaller` and GitHub CLI token lifting (`psl auth login --gh`).
    - Expanded test suite to 272 hermetic tests in ~1.5s with zero regressions.
  - [x] **Telemetry Consolidation, Modular Skills & Cross-Model Failure Mining (Phase 10 - ADR-032)**:
    - Delivered 8 modular operational runbooks (`media-ops`, `storage-ops`, `audio-ops`, `display-ops`, `sec-forensics`, `db-ops`, `mesh-ops`, `git-worktree-ops`).
    - Tightened background task log anti-polling to enforce Strict Reactive Wait Invariant on `.system_generated/tasks/*.log`.
    - Synchronized 100% of telemetry dataset (722 sessions, 219,292 steps) with central gateway and mined cross-model failure clusters.
    - Full test suite expanded to **401 hermetic tests passing in <1.0s** (<1.00s benchmark invariant strictly maintained).
  - [x] **Pre-Release v1.0.0-rc4: DRA Test Runner, Cleanroom REA Architecture & Single-Source Skills (Phase 11)**:
    - Delivered Dynamic Repository Awareness (DRA) native test detection (`detect_project_test_runner`, `is_harness_workspace`).
    - Integrated opt-in Cleanroom REA architecture under `--experimental-rea` (ADR-028) with <0.05s fast-path doctor diagnostics.
    - Resolved P0 duplicate skill context leak (~4,500 tokens/turn saved) via `check_duplicate_skills`, `enforce_single_source_skills`, and `--prune-duplicates`.
    - Accelerated telemetry sync by 3,000x (79ms) with composite unique indexes and chunked batch insertion.
    - Remediated shadow audit findings (DEF-01 through DEF-04) and implemented canonical `agyis verify` CLI.
    - Reached **847 hermetic tests passing in 12.7s**, doctor 9 OK / 0 missing, and federated 1,443 sessions (346k steps).

  - [x] **Fleet Harmonization, Multi-Repo Onboarding & Release Candidate v1.0.0-rc5 Preparation (Phase 12 - Horizon 1.5)**:
    - Executed 18-repository fleet audit and rehydrated/rebased 16 active PRs across 5 highest-velocity repos (`sunshine-physio-webapp`, `knot-mesh`, `purrfectcore-001`, `psl-website`, `mm-website`), publishing [`docs/specs/rc4_rehydration_findings.md`](docs/specs/rc4_rehydration_findings.md).
    - Staged 7 publication-grade GitHub issues (#57–#63) under milestone `v1.0.0-rc5` with 100% manifest parity (`docs/specs/rc5_github_issues_manifest.md`), dual-audited by `victory_auditor_16` and cockpit auditor `3402c677`.
    - Delivered all 4 Category B core remediations in `harness/` (unified `agyis onboard` CLI, `.agents/archive/` backup lifecycle, Python test extraction GAP-07, and background sync service management #57), dual-audited by `victory_auditor_17` and cockpit auditor `e771d12d`.
    - Conducted 3 cleanroom REA investigations on Antigravity desktop: verified 50k token compaction window, located hidden native context visualizer (`j5b`), and unlocked Trajectory Debug View & DevTools via live CDP.
    - Expanded test suite to **903 hermetic tests passing in 14.107s** (exit code 0; <15s budget; sub-second unit benchmark <0.02s–0.75s). Doctor reports 9 OK / 0 missing; 0 external runtime dependencies.

  - [x] **Agent Architecture Overhaul, REA GUI Telemetry & Trajectory Persistence (Phase 13 - Horizon 1.6)**:
    - **Subagents Engine Modernization**: Injected `send_message` across all capability bundles and 7 specialist personas in `harness/subagents/spec.py`; resolved permission paradox (`write: true` when `enable_write_tools: true`).
    - **Native Primitives & Empirical Rules Alignment**: Synchronized all personas in `harness/agents/` and `.agents/agents/` with `/teamwork-preview`, `/boost`, and the 8 Canonical Empirical Rules.
    - **Token Proximity Guard**: Implemented PreToolUse hook monitoring session context consumption with amber (>35k) and red pulse (>45k) terminal alerts.
    - **GUI Telemetry & Autonomous Persistence (`agyis gui`)**: Implemented 100% stdlib RFC 6455 CDP WebSocket controller, `--toggle`, `--wait` hydration retry loop, `--no-popup` startup priming, DOM hotkey listeners (`F12`, `Ctrl+Shift+T`), Command Palette feature flag unlocking, `~/.local/bin/agy-debug` shortcut, and `antigravity-trajectory.path` systemd user service.
    - **Test Benchmark & Certification**: Expanded test suite to **1,006 hermetic tests passing in 15.16s** (exit code 0; GUI unit tests pass in 0.043s). Certified by Triple Auditor Gate and deployed globally to `~/.gemini/config/plugins/psl-agy-harness/`.

  - [x] **Documentation & Runbook Hydration, Test Noise Suppression & v1.0.0-rc5 Release (Phase 14 - Horizon 1.7)**:
    - **Test Output Noise Suppression (Clean Dots Invariant)**: Isolated stdout/stderr across negative test cases (`tests/test_onboard.py`, `tests/test_verify.py`, `tests/test_anti_drift.py`, `tests/test_sync_service.py`, `tests/test_pipeline_audit_smoke.py`) using `redirect_stdout`/`redirect_stderr` and `mock.patch`. Running `python3 -m harness.cli test` produces clean unbroken test dots across all **1,065 tests** with exit code 0 and zero leaked JSON error objects or failure banners.
    - **Codification of 5 Strategic Fleet Recommendations**:
      1. *Universal Golden Path*: Promoted `agyis onboard` as turnkey golden path in `docs/runbooks/repo-onboarding.md`, agent instructions, and user guides with branch isolation, dirty-tree safety patch generation, 4-phase legacy pruning, and automated PR delivery.
      2. *Automated DB Port Collision Remediation*: Standardized `detect_port_collision.py --rebind` in developer runbooks and doctor diagnostics to resolve Prisma P1000 errors on developer workstations.
      3. *Single-Source Skill Deduplication*: Enforced single-source hygiene (`enforce_single_source_skills` / `agyis skills --prune-duplicates`), eliminating ~4,500 tokens/turn context bleed and defining the 3-tier boundary (Project Specialist > User Environment > Global Plugin).
      4. *Mandatory Build Cache Invalidation*: Codified mandate in rules and runbooks requiring Next.js/Turborepo cache purging (`.next/`, `.turbo/`, `node_modules/.cache`) prior to verification gates in PR rebase workflows.
      5. *Native Background Telemetry Daemon*: Promoted `agyis sync --service [install|status|start|stop|uninstall]` via systemd user units as the standard persistent sync mechanism.
    - **Synchronized Documentation Bundle & 18-Command CLI Palette**:
      - Updated `README.md` to reflect 1,065 tests, 18 CLI subcommands, GUI devtools, cleanroom verification, port collision checks, and updated benchmark data.
      - Overhauled `docs/official-specs/cli-palette.md` to canonical 18-subcommand specification (`doctor`, `hook`, `test`, `audit`, `skills`, `agents`, `subagents`, `status`, `remote`, `auth`, `sync`, `init`, `harmonize`, `onboard`, `install`, `uninstall`, `verify`, `gui`).
      - Updated `docs/official-specs/lifecycle-hooks.md` with all 6 active hooks, `token-proximity-guard`, and ADR-028 decoupled dirty state (`spec_dirty` vs `code_dirty`).
      - Modernized `docs/runbooks/repo-onboarding.md` and `docs/runbooks/telemetry-sync.md`.
      - Harmonized `AGENTS.md` and `.agents/rules/AGENTS.md` with v1.0.0-rc5 CLI commands and invariants.
    - **Automated Verification Gates & Certification**: Verified 1,065 hermetic tests passing with 100% green exit code 0, host doctor passing with 9 OK / 0 missing, and all 11 cleanroom specifications in `docs/specs/` verified (`agyis verify --spec`). Full release readiness achieved for `v1.0.0-rc5`.

---

### ⚪ Horizon 2: Fleet Scaling & Knot Hardware Mesh (FUTURE)
* **Goal**: Expand from single-workstation optimization to distributed cluster execution across the physical Knot mesh.
* **Resolution**: **Low Resolution (Strategic Vision)**.
* **Key Milestones**:
  - Remote strand telemetry routing (`laptop`, `rog-ally`, `steamdeck`).
  - Out-of-band multi-agent coordination via Linda Tuplespace and GitHub Discussions (`swarm-council`).
  - Decoupled visual cockpits on worker displays.
