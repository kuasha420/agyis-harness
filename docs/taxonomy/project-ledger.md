<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# 📜 PSL Harness Project Ledger (Compacted Horizon 0)

This ledger preserves permanent architectural decisions, schema contracts, and verified baseline metrics across completed phases. Detailed operational logs fade into git history and archives.

---

## [Phase 1] Foundation, Baseline Telemetry & Ecosystem Audit
* **Status**: Completed | **Compaction Date**: 2026-10-02
* **Key Architectural Decisions (ADRs)**:
  - **ADR-001 (License & Stance)**: Apache-2.0 open-source initiative. Build on and extend official Google Antigravity surfaces (`plugin.json`, hooks, rules) rather than building an isolated competing framework.
  - **ADR-002 (Telemetry Schema)**: Structured SQLite database (`data/telemetry.db`) mapping sessions, steps, tool calls, and human interventions.
  - **ADR-003 (Dynamic Aperture Planning)**: Adopted Resolution Gradient with Retroactive Horizon Compaction—high-res present, mid/low-res future, and compacted permanent ledger past.
* **Empirical Baselines Established**:
  - **Volume**: 348 sessions, 140,005 steps, 64,065 tool calls, 2,232 tool failures, 1,690 operator interventions.
  - **Root Cause**: `run_command` accounts for 98.4% of all tool failures (1,541 Exit Code 1, 143 Exit Code 127).
  - **Loop Traps**: 5,773 repeated consecutive calls (3,951 `view_file`, 625 `grep_search`, 300 `manage_task`).
  - **Context Cliff**: Trajectories >200 steps suffer a 20x error spike (1.0 -> 20.5) and 40x intervention spike (0.4 -> 16.3).
  - **Rule Calibration**: Explicit command dictionaries (e.g. `purrmission`) yield 1.67 interventions/session; multi-file rule indirection (e.g. `mm-website`) causes 18.2 interventions/session (10x higher).
* **Reference Harness Assets Committed**:
  - Manifest: [plugin.json](../../plugin.json)
  - Rules: [.agents/rules/AGENTS.md](../../.agents/rules/AGENTS.md)
  - Lifecycle Hooks: [harness/hooks/anti_loop_hook.py](../../harness/hooks/anti_loop_hook.py), [harness/hooks/command_safety_hook.py](../../harness/hooks/command_safety_hook.py), [hooks.json](../../hooks.json).
  - Skill: [.agents/skills/psl-audit-toolkit/SKILL.md](../../.agents/skills/psl-audit-toolkit/SKILL.md)

---

## [Phase 2] Context Dynamics, Cognitive Traces & Plan Drift
* **Status**: Completed | **Compaction Date**: 2026-10-02
* **Key Architectural Decisions (ADRs)**:
  - **ADR-009 (Cognitive Circuit Breaker)**: Enforce PreToolUse tripping when consecutive tool calls lack parameter mutation, breaking the "Repetition Trap" where thinking detects failure but action repeats it.
  - **ADR-010 (Attention Sink Desync Fence)**: Detect attention sink collapse (e.g. 85.5% thought perseveration in long sessions) and force state synchronization before runaway step counts.
* **Empirical Baselines Established**:
  - **Token Volume**: 32.4M tokens analyzed across 348 sessions; 100k token cliff confirmed (40x intervention surge >200k tokens).
  - **Output Compaction Feasibility**: 2KB output compactor modeled to eliminate 6.9M tokens (21.3% of total context volume).
  - **Cognitive Traces**: 14,476 thinking traces extracted and analyzed; mapped 5 primary failure modes (Repetition Trap, Exit Code 1 Panic, Hallucinated Environment, Attention Sink Collapse, False Rationalization).
  - **Planning & Drift**: 474 artifacts audited across 155 sessions (94 plan-walkthrough pairs).
* **Canonical Specifications Committed**:
  - [context-cliff-dynamics.md](context-cliff-dynamics.md)
  - [cognitive-traces-report.md](cognitive-traces-report.md)
  - [cognitive-failure-taxonomy-deepdive.md](cognitive-failure-taxonomy-deepdive.md)
  - [planning-and-drift-report.md](planning-and-drift-report.md)

---

## [Phase 3] Antigravity Platform Surface Mapping & Empirical Gap Analysis
* **Status**: Completed | **Compaction Date**: 2026-10-02
* **Key Architectural Decisions (ADRs)**:
  - **ADR-004 (Extension Surface Bifurcation)**: Formalized the three-tier boundary model: Tier 1 (Native Platform Primitives: reactive task wakeups, compaction thresholds, OS command sandboxes), Tier 2 (Deterministic Lifecycle Hooks: pre/post-tool safety, argument rewrite `overwrite`, loop tripping, stop fences), and Tier 3 (External Services: MCP servers for hardware mesh & tuplespace).
  - **ADR-005 (Reactive Wakeup Supremacy)**: Prohibited agent polling loops on `manage_task(Action='status')` in favor of Antigravity 2.0 reactive wakeups.
  - **ADR-006 (Argument Rewrite Interception)**: Standardized on `PreToolUse` shallow `overwrite` dictionaries to sanitize benign pattern-matching pipelines (`|| true`), enforce non-interactive pagers (`PAGER=cat`), and inject network timeouts (`-o ConnectTimeout=5`).
* **Canonical Specifications Committed**:
  - [docs/official-specs/platform-surface-mapping.md](../../docs/official-specs/platform-surface-mapping.md): 655-line definitive deconstruction of CLI (`agy`), 2.0 Desktop Platform, Python SDK (`google-antigravity`), Lifecycle Hooks (`hooks.json`), and MCP boundaries mapped against the 348-session audit.

---

## [Phase 4] POC Lifecycle Hook: PostToolUse Output Compactor
* **Status**: Completed | **Compaction Date**: 2026-10-02
* **Key Architectural Decisions (ADRs)**:
  - **ADR-007 (Deterministic 2KB Output Compactor)**: Standardized on `PostToolUse` deterministic 2KB output compaction for `run_command` and `view_file`. Preserves head (500 chars), tail (1,000 chars), and all intermediate lines containing exit code/fatal/error/failure markers.
  - **ADR-008 (Diagnostic Failure Invariant)**: Invariant: any tool execution with non-zero exit code or error status is preserved 100% in full without compaction.
* **Verified Baseline Metrics**:
  - Eliminates 84.5%–96.9% of payload volume on outputs >10KB (~6.9M tokens saved across corpus).
  - Micro-benchmark latency <0.25 ms (241 µs at 50KB; 1.1 µs decision latency for failures).
  - 100% pass rate across 13 automated unit and contract integration tests.
* **Reference Assets Committed**:
  - Hook Implementation: [harness/hooks/output_compactor_hook.py](../../harness/hooks/output_compactor_hook.py)
  - Test Suite: [tests/test_output_compactor.py](../../tests/test_output_compactor.py)
  - Hook Registry: [hooks.json](../../hooks.json)
  - Benchmark Report: [output-compactor-poc-results.md](output-compactor-poc-results.md)

---

## [Phase 4.2] Hermetic Runtime Guarantee & Command Safety Hook
* **Status**: Completed | **Compaction Date**: 2026-10-02
* **Key Architectural Decisions (ADRs)**:
  - **ADR-011 (The Hermetic Runtime Guarantee)**: Toolchain compatibility is guaranteed by the harness product, not offloaded to model prompting. Bifurcated strategy: transparently injects CPython >= 3.12 from `uv`'s cache for inline utility one-liners (`python3 -c`) to eliminate PEP 701 f-string crashes, while respecting project-local `.venv` for repository builds.
  - **ADR-012 (The Artifact-First Planning Invariant)**: Prohibits architectural and execution proposals in raw chat turns. All non-trivial proposals must be anchored in structured artifacts before requesting confirmation.
  - **ADR-013 (Surgical Shell Sanitization)**: Terminal standalone pattern searches (`grep`/`diff`) without conditionals are sanitized via `|| [ $? -eq 1 ]`, neutralizing benign zero-match failures while preserving exit code 2 errors and complex compound scripts.
* **Verified Baseline Metrics**:
  - 100% of PEP 701 f-string syntax errors eliminated via transparent uv CPython 3.12 injection.
  - Exit code 1 forensic de-aggregation: 329 grep misses (21.3%), 58 python syntax errors (3.8%), 142 tracebacks (9.2%).
  - `psl doctor` CLI audits 10 core binaries across 3 telemetry tiers with zero-sudo auto-healing.
* **Reference Assets Committed**:
  - Runtime Matrix: [harness/runtime/matrix.json](../../harness/runtime/matrix.json)
  - Workstation Doctor: [harness/runtime/doctor.py](../../harness/runtime/doctor.py)
  - Command Safety Hook: [harness/hooks/command_safety_hook.py](../../harness/hooks/command_safety_hook.py)

---

## [Phase 5.1] Testing Codification, Anti-Loop Test Suite & Unified Developer CLI
* **Status**: Completed | **Compaction Date**: 2026-10-02
* **Key Architectural Decisions (ADRs)**:
  - **ADR-014 (Product vs Project Bifurcation)**: Formalized strict boundary between The Product (distributable runtime plugin, CLI toolchain, deterministic hooks, product rules/skills) and The Project (local empirical lab, `data/telemetry.db`, research specs).
  - **ADR-015 (Hermetic Test Isolation Invariant)**: Enforced tempfile isolation, dynamic state directory overrides (`PSL_HARNESS_STATE_DIR`), sub-second benchmark (<1.0s), and official protojson contract assertions across all hooks.
  - **ADR-016 (Unified Hook Dispatch Architecture)**: Standardized hook execution in `hooks.json` via `python3 -m harness.cli hook <name>`, eliminating fragile relative script paths and CWD desyncs.
* **Verified Baseline Metrics**:
  - 43 tests passing with 100% coverage in 0.838s (<1.0s benchmark invariant met).
  - 100% test coverage across all 3 lifecycle hooks (`anti_loop_hook`, `command_safety_hook`, `output_compactor_hook`).
  - Unified CLI `psl` operational (`doctor`, `hook`, `test`, `audit`, `status`).
* **Reference Assets Committed**:
  - Unified CLI: [harness/cli.py](../../harness/cli.py)
  - Testing Contract: [docs/official-specs/testing-contracts.md](../../docs/official-specs/testing-contracts.md)
  - Test Suites: [tests/test_anti_loop.py](../../tests/test_anti_loop.py), [tests/test_cli.py](../../tests/test_cli.py)

---

## [Phase 5.2] Modular Product Skills & Specialist Agent Scaffold
* **Status**: Completed | **Compaction Date**: 2026-10-02
* **Key Architectural Decisions (ADRs)**:
  - **ADR-017 (Progressive Stack Disclosure)**: Offloaded stack-specific rules from monolithic prompts into on-demand modular skills (`harness/skills/`), keeping primary context in the healthy zone (<50k tokens).
  - **ADR-018 (Specialist Subagent Archetypes)**: Codified 3 bounded specialist archetypes (`Executioner` with write/exec, `Hammer` strictly read-only, `Auditor` exec-only for verification). Enforced `can_subagent=False` across all archetypes to eliminate runaway recursive subagent trees.
  - **ADR-019 (Subagent Ladder Pipeline)**: Executed via the multi-agent SWE pipeline (`Executioner -> Hammer -> Auditor`), enforcing anti-bypass and zero-coordinator-remediation invariants.
* **Verified Baseline Metrics**:
  - 61 tests passing with 100% coverage in 0.904s (<1.0s benchmark invariant met).
  - 8 modular skills cataloged; 3 specialist agent archetypes registered with zero-dep YAML frontmatter parser.
  - Subagent Ladder pipeline executed end-to-end with 100% first-pass Hammer and Auditor approvals.
* **Reference Assets Committed**:
  - Skills Engine: [harness/skills/__init__.py](../../harness/skills/__init__.py), [harness/skills/psl-stack-shell/SKILL.md](../../harness/skills/psl-stack-shell/SKILL.md), [harness/skills/psl-stack-typescript/SKILL.md](../../harness/skills/psl-stack-typescript/SKILL.md), [harness/skills/psl-stack-python/SKILL.md](../../harness/skills/psl-stack-python/SKILL.md), [harness/skills/psl-stack-backend/SKILL.md](../../harness/skills/psl-stack-backend/SKILL.md), [harness/skills/psl-stack-systems/SKILL.md](../../harness/skills/psl-stack-systems/SKILL.md)
  - Subagent Registry: [harness/subagents/](../../harness/subagents/), [harness/agents/harness_builder.md](../../harness/agents/harness_builder.md), [harness/agents/harness_reviewer.md](../../harness/agents/harness_reviewer.md), [harness/agents/harness_auditor.md](../../harness/agents/harness_auditor.md)
  - CLI Discovery: [harness/cli.py](../../harness/cli.py) (`psl skills`, `psl agents`)
  - Test Suites: [tests/test_skills.py](../../tests/test_skills.py), [tests/test_subagents.py](../../tests/test_subagents.py)

---

## [Phase 5.3] Telemetry Deep Mining & Character Volume Distribution
* **Status**: Completed | **Compaction Date**: 2026-10-02
* **Key Architectural Decisions (ADRs)**:
  - **ADR-020 (Empirical Volume Telemetry Schema)**: Enriched `tool_calls` schema non-destructively (`output_length_chars`, `output_lines`, `arguments_length_chars`, `command_category`, `is_truncated`) with idempotent migration and automatic backfill across 347 historical sessions.
  - **ADR-021 (Failure Compaction Exemption Audit)**: Validated empirical compaction simulation across 64,065 tool calls; proved 2KB compactor eliminates 35.75M characters (~8.94M tokens, 35.75% reduction) with strictly 0 violations of the Failure Preservation Invariant (ADR-008).
* **Verified Baseline Metrics**:
  - 67 tests passing with 100% coverage in 0.932s (<1.0s benchmark invariant met).
  - 100,018,724 characters analyzed across 64,065 calls; `view_file` (48.5M chars, 64.7% >2KB) and `run_command` (33.3M chars, 20.3% >2KB) identified as primary volume bloaters.
  - Test runner commands (`test_runner`) and search probes (`grep_search`) identified as highest category bloaters (>30% exceeding 2KB).
* **Reference Assets Committed**:
  - Ingestion & Backfill Engine: [pipeline/extract_transcripts.py](../../pipeline/extract_transcripts.py)
  - Volume Analyzer: [pipeline/analyze_volume_distributions.py](../../pipeline/analyze_volume_distributions.py)
  - CLI Integration: [harness/cli.py](../../harness/cli.py) (`psl audit volume`)
  - Canonical Report: [tool-volume-distribution-report.md](tool-volume-distribution-report.md)
  - Test Suite: [tests/test_volume_mining.py](../../tests/test_volume_mining.py)

---

## [Phase 1] Deterministic Stop-Hook Verification Fence
* **Status**: Completed | **Compaction Date**: 2026-10-02
* **Key Architectural Decisions (ADRs)**:
  - **ADR-022 (Stop Verification Fence & State Machine)**: Deterministic gate on agent completion (`Stop`). Edits to code files (`.py`, `.ts`, `.rs`, `.go`, etc.) mark state dirty; docs (`.md`), assets (`.png`), and lockfiles are exempt. Agents cannot stop without clean verification (`./psl test`). Includes 2-block anti-deadlock safety valve and live `PreToolUse` file-write interception (`write_to_file`, `replace_file_content`, `edit_file`).
* **Empirical Baselines Established & Verified**:
  - Live interception via `PreToolUse` for `write_to_file`, `replace_file_content`, and `edit_file`.
  - Automatic dirty-flag clearance across active conversations upon successful `./psl test` execution.
  - Sub-second performance (<1.0s benchmark across 91 unit and contract tests).
* **Reference Assets Committed**:
  - Hook Implementation: [harness/hooks/completion_fence_hook.py](../../harness/hooks/completion_fence_hook.py)
  - Lifecycle Configuration: [hooks.json](../../hooks.json)
  - CLI Dispatch & Test Clearance: [harness/cli.py](../../harness/cli.py)
  - Test Suite: [tests/test_completion_fence.py](../../tests/test_completion_fence.py)

---

## [Phase 2] Terminal Execution & Subshell PATH Reliability (ADR-023)
* **Status**: Completed | **Compaction Date**: 2026-10-02
* **Key Architectural Decisions (ADRs)**:
  - **ADR-023 (Terminal Execution & Subshell PATH Reliability)**: Eliminates non-login subshell Exit 127 ("command not found") by transparently discovering and injecting user-space PATH shims (`~/.local/bin`, `~/.cargo/bin`, `~/.local/share/pnpm`, `~/.pyenv/shims`) for toolchains (`uv`, `pnpm`, `cargo`, `pytest`, etc.) via `export PATH="<shims>:$PATH"; <cmd>`. Eliminates hanging background tasks and Exit 255 network probe stalls by injecting non-blocking SSH timeout and BatchMode options (`-o ConnectTimeout=5 -o BatchMode=yes -o ServerAliveInterval=2 -o ServerAliveCountMax=2`).
* **Empirical Baselines Established & Verified**:
  - 100% resolution of user toolchain Exit 127 in non-login subshells without mutating user shell configuration files.
  - SSH network hangs converted to deterministic fast-fails within 5 seconds.
  - Full pipeline idempotency verified; existing dangerous pattern blocking and hermetic runtime guarantees preserved.
  - 96 tests passing with 100% coverage in <1.0s benchmark (0.74s actual).
* **Reference Assets Committed**:
  - Hook Implementation: [harness/hooks/command_safety_hook.py](../../harness/hooks/command_safety_hook.py)
  - Test Suite: [tests/test_command_safety.py](../../tests/test_command_safety.py)
  - Specification: [docs/official-specs/lifecycle-hooks.md](../../docs/official-specs/lifecycle-hooks.md)
---

## [Phase 3] Plan-to-Execution Anti-Drift & Cognitive Anchors (ADR-024)
* **Status**: Completed | **Compaction Date**: 2026-10-03
* **Key Architectural Decisions (ADRs)**:
  - **ADR-024 (Plan-to-Execution Anti-Drift & Cognitive Anchors)**: Enforces plan boundary fidelity during code generation. Intercepts file mutation tools (`write_to_file`, `replace_file_content`, `edit_file`) in `PreToolUse`. Automatically discovers active plan (`find_active_plan`) and parses declared boundary paths (`parse_plan_files`) across markdown links, action headers, and backticked paths. Protects against accidental mutation while granting zero-friction exemptions (`is_exempt_file`) for documentation (`.md`, `.txt`), artifacts (`.agents/artifacts/*`, brain dirs), and temporary scratch spaces (`scratch/*`, `tmp/*`).
* **Empirical Baselines Established & Verified**:
  - Live `PreToolUse` interception registered in `hooks.json` via `python3 -m harness.cli hook anti-drift`.
  - Configurable strict mode (`PSL_STRICT_ANTI_DRIFT=1`) emitting operator confirmation requests (`ask`) and non-strict mode emitting advisory notices (`allow`).
  - Cognitive attention horizon indicators integrated into `psl status`.
  - 111 tests passing with 100% coverage in <1.0s benchmark (0.91s actual).
* **Reference Assets Committed**:
  - Hook Implementation: [harness/hooks/anti_drift_hook.py](../../harness/hooks/anti_drift_hook.py)
  - Registry & Dispatch: [hooks.json](../../hooks.json), [harness/cli.py](../../harness/cli.py)
  - Test Suite: [tests/test_anti_drift.py](../../tests/test_anti_drift.py)
  - Specification: [lifecycle-hooks.md](../official-specs/lifecycle-hooks.md)

---

## [Phase 4] Subagent Lifecycle Ergonomics, Zero-Token Context Gauge & Execution Reliability (ADR-025)
* **Status**: Completed | **Compaction Date**: 2026-10-03
* **Key Architectural Decisions (ADRs)**:
  - **ADR-025 (Subagent Lifecycle Ergonomics, Zero-Token Context Gauge & Execution Reliability)**:
    - **Zero-Token Context Gauge (`estimate_subagent_context`)**: Evaluates subagent context window consumption and lifecycle recommendations (`HEALTHY/REUSE`, `AMBER/COMPACT_RECREATE`, `RED_ALERT/RETIRE`) with zero LLM API tokens. Uses exact streaming JSON parser for transcripts $\le 2\text{MB}$ ($<1\text{ms}$) and fast size-stat heuristic for titan runaway transcripts $>2\text{MB}$ ($<0.05\text{ms}$).
    - **Auditor Permissions Paradox & Write-Block Guard (`check_auditor_write_block`)**: Resolves the permissions paradox where `harness_auditor` needs execution permissions (`run_command`) for automated testing without having file mutation access. Intercepts file mutation tools (`write_to_file`, `replace_file_content`, `edit_file`) in `PreToolUse` while preserving read and command execution.
    - **Zero-Exploration Invariant**: Strictly forbids blind repository listing sweeps (`list_dir`, `find_by_name`) across all specialist agent archetypes (`harness_builder`, `harness_reviewer`, `harness_auditor`), requiring agents to open target files directly from plan and prompt directives.
    - **Live Developer Cockpit Telemetry (`psl subagents`)**: Standardizes active subagent discovery in CLI (`psl subagents [--json]`) and embeds real-time context health gauges in `psl status`.
* **Empirical Baselines Established & Verified**:
  - Context estimation latency strictly $<3.5\text{ms}$ on real 350KB transcripts; $<0.02\text{ms}$ on mock suites.
  - 100% block accuracy on unauthorized auditor file mutations with descriptive invariant reasoning.
  - Sub-second benchmark invariant maintained: 135 unit and integration tests passing in 0.912s (<1.0s benchmark).
* **Reference Assets Committed**:
  - Subagent Context & Health Engine: [harness/subagents/](../../harness/subagents/)
  - PreToolUse Write-Block Guard: [harness/hooks/anti_drift_hook.py](../../harness/hooks/anti_drift_hook.py)
  - Specialist Agent Definitions: [harness/agents/harness_auditor.md](../../harness/agents/harness_auditor.md), [harness/agents/harness_builder.md](../../harness/agents/harness_builder.md), [harness/agents/harness_reviewer.md](../../harness/agents/harness_reviewer.md)
  - CLI Subagent Discovery: [harness/cli.py](../../harness/cli.py) (`psl subagents`)
  - Test Suites: [tests/test_subagent_context.py](../../tests/test_subagent_context.py), [tests/test_anti_drift.py](../../tests/test_anti_drift.py), [tests/test_subagents.py](../../tests/test_subagents.py), [tests/test_cli.py](../../tests/test_cli.py)
  - Specification: [docs/official-specs/lifecycle-hooks.md](../../docs/official-specs/lifecycle-hooks.md)

---

## [Phase 5] Custom Codebase & Workspace-Aware Agents (ADR-026)
* **Status**: Completed | **Compaction Date**: 2026-10-03
* **Key Architectural Decisions (ADRs)**:
  - **ADR-026 (Custom Codebase & Workspace-Aware Agents Architecture)**:
    - **Dual-Mode Discovery Invariant**: Agents defined in `.agents/agents/*.md` are discovered simultaneously as background subagents (`invoke_subagent`) and top-level conversational entrypoint personas (`mainAgent: true`) in the Antigravity chat UI and CLI `/agents` panel.
    - **Protobuf Enum Boundary & Model Inheritance**: Hardcoded `invoke_subagent` protobuf enum (`inherit`, `flash_lite`, `flash`, `pro`) prohibits dynamic `--effort` parameters; `Model: "inherit"` is codified as the workhorse pattern to automatically propagate session model and reasoning tier.
    - **Accuracy vs. Latency Paradox**: Empirical benchmark (`data/reasoning_benchmark_results.json`) demonstrated `gemini-3.8-flash-low` achieved 100% accuracy identically to High effort, while running 2.55x faster (3.63s vs 9.26s) and consuming 3.1x fewer thinking tokens.
    - **Platform Tool Hanging Hardening**: Codified verified 20-tool catalog (`ANTIGRAVITY_PLATFORM_TOOLS`) and capability bundles (`read_only`, `verifier`, `builder`, `orchestrator`) with compile-time linting in `validate_agent_spec` to eliminate the official tool typo hang.
    - **Automated Workspace Inspection**: `inspect_workspace_context()` extracts manifests, test commands, ADRs, and active rules to ground scaffolded prompts.
    - **Multi-Role Write-Block Guard**: Generalized `check_auditor_write_block` in `anti_drift_hook.py` to block mutations across `planner`, `coordinator`, `auditor`, and `reviewer`.
* **Empirical Baselines Established & Verified**:
  - 149 hermetic tests passing in 0.968s (strictly < 1.0s benchmark invariant).
  - 10/10 agent specifications certified valid across product and project directories.
  - Subagent Ladder trajectory offloaded 64.4% of context volume (~201k tokens preserved) with 0 coordinator tool errors.
* **Reference Assets Committed**:
  - Research Specification: [docs/official-specs/custom-agents.md](../../docs/official-specs/custom-agents.md)
  - Expanded Catalog: [harness/agents/planner.md](../../harness/agents/planner.md), [harness/agents/coordinator.md](../../harness/agents/coordinator.md)
  - Registry, Context Scanner & Scaffolder: [harness/subagents/](../../harness/subagents/)
  - CLI Subcommands: [harness/cli.py](../../harness/cli.py) (`agents create`, `agents validate`, `agents --sync`)
  - Modular Skill: [harness/skills/agent-builder/SKILL.md](../../harness/skills/agent-builder/SKILL.md)
  - Unit Test Suite: [tests/test_agent_scaffold.py](../../tests/test_agent_scaffold.py)


---

## [Phase 6] Global Plugin Delivery, Coexistence Engine & 6-Stage Subagent Ladder (ADR-030)
* **Status**: Completed | **Compaction Date**: 2026-10-05
* **Key Architectural Decisions (ADRs)**:
  - **ADR-030 (Global Plugin Delivery & Coexistence Hierarchy)**:
    - **Product vs. Project Packaging Bifurcation**: Distributable package (`harness/`, `plugin.json`, `matrix.json`, `hooks.json`) is hermetically separated from dev pipelines (`pipeline/`, `data/`, `tests/`, `docs/`, `scratch/`).
    - **Path Safety Guard**: `PluginInstaller` strictly forbids deleting `REPO_ROOT` or parent directories; symlink uninstallations invoke `target.unlink()` and never `shutil.rmtree(target.resolve())`.
    - **Three-Tier Precedence Hierarchy**: Layer 3 (Workspace Local `.agents/`) > Layer 2 (User Preferences `~/.gemini/antigravity/`) > Layer 1 (Global Plugin `~/.gemini/config/plugins/psl-agy-harness/`).
    - **Stage 4 Custodian Commit Gate**: Positioned between Hammer (Stage 3) and Auditor (Stage 5) to guarantee Stage 5 tests execute against an immutable committed git revision on HEAD, eliminating the tested-vs-uncommitted desync.
    - **Targeted Macro & Deduplication Sweep Invariant**: Custodian is explicitly mandated to perform targeted sweeps (`grep_search`, `find_by_name`) for DRY deduplication and cross-module architectural audits before staging commits.
* **Empirical Baselines Established & Verified**:
  - Full test suite expanded to **237 unit and integration tests passing in 1.456s** (~6.1ms/test throughput).
  - 10 new hermetic delivery tests executing in 0.056s.
  - 7 specialist subagents cataloged and certified valid (`coordinator`, `custodian`, `harness_auditor`, `harness_builder`, `harness_reviewer`, `planner`, `psl_main`).
  - Working tree verified 100% clean on commit `8fb2bde`.
* **Reference Assets Committed**:
  - Plugin Installer & Coexistence Subsystem: [harness/delivery/](../../harness/delivery/)
  - CLI Integration: [harness/cli.py](../../harness/cli.py) (`psl install`, `psl uninstall`)
  - Custodian Archetype & Scaffolding: [harness/subagents/](../../harness/subagents/), [harness/agents/harness_custodian.md](../../harness/agents/harness_custodian.md), [.agents/agents/harness_custodian.md](../../.agents/agents/harness_custodian.md)
  - PreToolUse Write-Block Guard: [harness/hooks/anti_drift_hook.py](../../harness/hooks/anti_drift_hook.py)
  - 6-Stage Subagent Ladder Specification: [harness/skills/subagent-ladder/SKILL.md](../../harness/skills/subagent-ladder/SKILL.md)
  - Test Suite: [tests/test_delivery.py](../../tests/test_delivery.py)

---

## [Phase 7] Centralized Telemetry Gateway, GitHub Org Auth & Client Transport (ADR-030 Final Closure)
* **Status**: Completed | **Compaction Date**: 2026-10-05
* **Key Architectural Decisions (ADRs)**:
  - **ADR-030 (Lane 1 + Lane 5 Closure: Centralized Gateway & Sync Transport)**:
    - **In-Tree Centralized Telemetry Gateway (`server/`)**: Starlette ASGI service with dual-engine storage (PostgreSQL in production/Docker, in-memory SQLite for hermetic tests). Exposes `/api/v1/health`, `/api/v1/auth/verify`, `/api/v1/sync/push`, and `/api/v1/sync/pull`.
    - **GitHub Org Authorization & Caching**: Enforces active organization membership (`purrfectsoft` default / `PSL_GITHUB_ORG`) via GitHub API with 300s TTL in-memory caching to eliminate rate limit exhaustion.
    - **Replication Hygiene & Anti-Echo Filter**: Upserts sessions via `ON CONFLICT DO UPDATE` while isolating `origin_developer != requesting_user` during pull replication to prevent echo loops.
    - **Client Zero-Dependency Transport**: `harness/telemetry/sync.py` uses strictly CPython standard library `urllib.request` (zero third-party imports). Mandatory client-side scrubbing (`redaction.py`) executes before JSON serialization.
    - **CLI Auth & Sync Suite**: `psl auth login|status|logout` (storing credentials in `~/.config/psl/credentials.json` with 0o600 permissions); `psl sync` default bi-directional sync with `--push`, `--pull`, `--interactive`, and legacy `--session-id` support.
    - **CloudPanel Staging Architecture**: Bound to loopback `127.0.0.1:8000` for CloudPanel NGINX reverse-proxy routing on `<STAGING_HOST_REDACTED>`.
* **Empirical Baselines Established & Verified**:
  - Full test suite expanded to **256 hermetic unit and integration tests passing in 1.289s**.
  - 100% test pass rate across independent standard unittest runner and harness runner.
  - Zero third-party dependencies in `harness/` asserted and certified.
* **Reference Assets Committed**:
  - Central Gateway: [server/app.py](../../server/app.py), [server/storage.py](../../server/storage.py), [server/auth.py](../../server/auth.py)
  - Containerization & Ops: [server/Dockerfile](../../server/Dockerfile), [server/docker-compose.yml](../../server/docker-compose.yml), [server/deploy.sh](../../server/deploy.sh), [server/psl-telemetry-hub.service](../../server/psl-telemetry-hub.service)
  - Client Sync Transport & CLI: [harness/telemetry/sync/](../../harness/telemetry/sync/), [harness/telemetry/config.py](../../harness/telemetry/config.py), [harness/cli.py](../../harness/cli.py)
  - Hermetic Test Suites: [tests/test_server_api.py](../../tests/test_server_api.py), [tests/test_telemetry_sync.py](../../tests/test_telemetry_sync.py), [tests/test_cli.py](../../tests/test_cli.py)

---

## [Phase 8] Native Orchestration Alignment: Boost Swarm & Plan Mode (ADR-031)
* **Status**: Completed | **Compaction Date**: 2026-10-05 (Finalized 2026-10-06)
* **Key Architectural Decisions (ADRs)**:
  - **ADR-031 (Native Orchestration Alignment: Boost Swarm & Plan Mode)**:
    - **Native Plan-Mode Lock Invariant**: PreToolUse Anti-Drift Guard (`anti_drift_hook.py`) intercepts active Plan Mode (`/plan` or `mode: "plan"`) and unapproved implementation plans as zero-mutation boundaries, deterministically blocking code edits outside `implementation_plan.md` and scratch directories.
    - **Dual Orchestration Taxonomy**: Bifurcated task execution into (1) Native `/boost` Stigmergic Swarm (probabilistic multi-worker parallel search, synthetic test oracles, and adversarial verification for hard concurrency/algorithmic problems) and (2) PSL 6-Stage Subagent Ladder (deterministic linear pipeline with Stage 4 Custodian Git commit gate on HEAD and Stage 5 clean-room testing).
    - **Adversarial Verifier Capability Bundle**: Codified `adversarial_verifier` bundle in `harness/subagents.py` to support fuzzer, property testing, and test generator personas inspired by the `/boost` verifier architecture.
    - **Telemetry Ingestion for Native Slash Commands**: `pipeline/extract_transcripts.py` classifies `BOOST_ORCHESTRATION` and `PLAN_INITIATION` native slash commands in `telemetry.db`.
    - **Decoupled Architecture Note**: `/agent-builder` and custom agents remain strictly decoupled from ADR-031/ADR-030, anchored solely in ADR-026.
* **Empirical Baselines Established & Verified**:
  - Full test suite expanded to **259 hermetic tests passing in 1.297s** (with 47 anti-drift and scaffolding tests passing in 0.028s).
  - 7/7 specialist subagent specifications validated and certified compliant.
  - Clean-room verification passed with zero regressions.
* **Reference Assets Committed**:
  - Research Specification: [docs/official-specs/antigravity-boost-and-plan.md](../../docs/official-specs/antigravity-boost-and-plan.md)
  - Formal Decision Record: [docs/adr/ADR-031-native-orchestration-alignment.md](../../docs/adr/ADR-031-native-orchestration-alignment.md)
  - PreToolUse Plan-Mode Lock: [harness/hooks/anti_drift_hook.py](../../harness/hooks/anti_drift_hook.py)
  - Subagent Registry & Capability Bundles: [harness/subagents/](../../harness/subagents/)
  - Telemetry Ingestion Classifier: [pipeline/extract_transcripts.py](../../pipeline/extract_transcripts.py)
  - Test Suites: [tests/test_anti_drift.py](../../tests/test_anti_drift.py), [tests/test_agent_scaffold.py](../../tests/test_agent_scaffold.py)


---

## [Phase 9] Production Hardening: Chunked Telemetry Push, Zero-PWD DB Resolution, Global Bin Delivery & GH Auth (ADR-030 Closure)
* **Status**: Completed | **Compaction Date**: 2026-10-06
* **Key Architectural Decisions & Operational Refinements**:
  - **Zero-PWD Database Path Resolution (Issue #8)**: Strictly banned probing `$PWD/data/telemetry.db`. Resolution hierarchy enforces explicit `--db` > `PSL_TELEMETRY_DB` > Repository Root (`REPO_ROOT/data/telemetry.db`) > XDG state dir (`~/.local/share/psl/telemetry.db`). `push_local_sessions` strictly enforces `must_exist=True` raising `FileNotFoundError` to eliminate phantom 0-session database creation.
  - **Chunked Batch Push & HTTP 413 Mitigation (Issue #7)**: Partitioned large telemetry corpora into client-side chunks (`DEFAULT_BATCH_SESSION_LIMIT = 10`, `DEFAULT_BATCH_STEP_LIMIT = 2500`). Sequential transmission commits SQLite `remote_synced_at` per batch, preventing multi-batch failure rollbacks. Added bounded transient retry (up to 2 attempts on 502/503/504 and network disconnects) with fast-fail on 4xx client errors.
  - **Global Executable Delivery (Issue #6 & Operator Directives)**: `PluginInstaller` installs standalone `psl` launcher into `~/.local/bin/psl` (`0o755`) in addition to plugin directory, providing globally available CLI in user `$PATH`. Supported `--global` / `-g` and `--bin-dir`.
  - **GitHub CLI Credential Lifting**: `psl auth login --gh` lifts tokens via `gh auth token` stdlib subprocess execution, bypassing manual token copy-paste.
  - **Multi-Tiered Endpoint Configuration**: 5-tier resolution hierarchy (CLI `--endpoint` > `PSL_SYNC_ENDPOINT` > Workspace `<workspace>/.psl/config.json` > Global `~/.config/psl/config.json` > default) with `--workspace` and `--global` scoping support in `psl auth login`.
* **Empirical Baselines Established & Verified**:
  - Full test suite expanded to **272 hermetic unit and integration tests passing in 1.492s–1.527s** (13 new unit/integration tests).
  - 100% test pass rate across independent standard unittest runner and harness runner.
  - Toolchain doctor verified 100% operational (9 OK, 1 pyenv shim warning, 0 missing).
  - Clean working tree verified on commit `23fe402`.
* **Reference Assets Committed**:
  - Configuration & Path Subsystem: [harness/telemetry/config.py](../../harness/telemetry/config.py)
  - Chunked Sync Transport: [harness/telemetry/sync/](../../harness/telemetry/sync/)
  - Global Plugin & Executable Delivery: [harness/delivery/](../../harness/delivery/)
  - CLI Integration: [harness/cli.py](../../harness/cli.py)
  - Test Suites: [tests/test_telemetry_sync.py](../../tests/test_telemetry_sync.py), [tests/test_delivery.py](../../tests/test_delivery.py), [tests/test_cli.py](../../tests/test_cli.py)

---

## [Phase 10] Telemetry Consolidation, Modular Skills & Cross-Model Analytical Mining (ADR-032)
* **Status**: Completed | **Compaction Date**: 2026-10-10
* **Key Architectural Decisions & Invariants**:
  - **Tool-Native Primacy Invariant & Anti-Polling Breaker (ADR-032)**: Tightened background task log inspection guard to require `.log` extension, resolving false positives on source files like `src/tasks/task-queue.ts`. Enforces Strict Reactive Wait Invariant.
  - **8 Modular Operational Runbooks**: Designed, verified, and mirrored 8 modular skills across `harness/skills/`, `.agents/skills/`, and host plugin: `media-ops`, `storage-ops`, `audio-ops`, `display-ops`, `sec-forensics`, plus 3 new empirical skills:
    - `db-ops`: Standardized non-interactive `psql`/`sqlite3` CLI invocations, connection pool saturation diagnostics, table lock triage, WAL checkpointing, and Docker container database inspection.
    - `mesh-ops`: Knot hardware mesh coordination, dynamic topology discovery, Tailscale and WireGuard ping probes, SSH multiplexing (ControlMaster), zero-disk stdin script streaming, and cross-strand sync.
    - `git-worktree-ops`: Multi-branch isolated worktrees, safe creation/removal/pruning, stash hygiene, and `index.lock` recovery.
  - **Central Telemetry Hub Multi-Developer Synchronization**: Resolved anti-echo blocking, deployed live server gateway, pulled 125 historical sessions (35,767 steps), and successfully pushed all 162 unsynced workstation sessions (27,543 steps, 12,812 tools) to central hub. 100% of dataset is now synchronized.
  - **Cross-Model Failure Mining**: Mined 722 sessions (>219k steps, >100k tool calls) across 11 model tiers (`data/model_failure_clusters.json`, `docs/taxonomy/model-failure-clusters-report.md`). Added `psl audit clusters` CLI stage.
* **Verified Baseline Metrics**:
  - Full test suite expanded to **401 hermetic unit and integration tests passing in <1.0s** (0.963s actual, 100% pass rate).
  - 100% bitwise parity verified between `harness/skills/` and `.agents/skills/`, and between `harness/rules/AGENTS.md` and `.agents/rules/AGENTS.md`.
* **Reference Assets Committed**:
  - New Skills: [harness/skills/db-ops/SKILL.md](../../harness/skills/db-ops/SKILL.md), [harness/skills/mesh-ops/SKILL.md](../../harness/skills/mesh-ops/SKILL.md), [harness/skills/git-worktree-ops/SKILL.md](../../harness/skills/git-worktree-ops/SKILL.md)
  - Failure Mining Pipeline: [pipeline/analyze_failure_clusters.py](../../pipeline/analyze_failure_clusters.py)
  - Research Taxonomy: [model-failure-clusters-report.md](model-failure-clusters-report.md)
  - Hook Hardening: [harness/hooks/anti_loop_hook.py](../../harness/hooks/anti_loop_hook.py)

