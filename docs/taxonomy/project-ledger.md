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
  - Manifest: [plugin.json](plugin.json)
  - Rules: [.agents/rules/AGENTS.md](.agents/rules/AGENTS.md)
  - Lifecycle Hooks: [harness/hooks/anti_loop_hook.py](harness/hooks/anti_loop_hook.py), [harness/hooks/command_safety_hook.py](harness/hooks/command_safety_hook.py), [harness/hooks/hooks.json](harness/hooks/hooks.json).
  - Skill: [.agents/skills/psl-audit-toolkit/SKILL.md](.agents/skills/psl-audit-toolkit/SKILL.md)

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
  - [docs/taxonomy/context-cliff-dynamics.md](docs/taxonomy/context-cliff-dynamics.md)
  - [docs/taxonomy/cognitive-traces-report.md](docs/taxonomy/cognitive-traces-report.md)
  - [docs/taxonomy/cognitive-failure-taxonomy-deepdive.md](docs/taxonomy/cognitive-failure-taxonomy-deepdive.md)
  - [docs/taxonomy/planning-and-drift-report.md](docs/taxonomy/planning-and-drift-report.md)

---

## [Phase 3] Antigravity Platform Surface Mapping & Empirical Gap Analysis
* **Status**: Completed | **Compaction Date**: 2026-10-02
* **Key Architectural Decisions (ADRs)**:
  - **ADR-004 (Extension Surface Bifurcation)**: Formalized the three-tier boundary model: Tier 1 (Native Platform Primitives: reactive task wakeups, compaction thresholds, OS command sandboxes), Tier 2 (Deterministic Lifecycle Hooks: pre/post-tool safety, argument rewrite `overwrite`, loop tripping, stop fences), and Tier 3 (External Services: MCP servers for hardware mesh & tuplespace).
  - **ADR-005 (Reactive Wakeup Supremacy)**: Prohibited agent polling loops on `manage_task(Action='status')` in favor of Antigravity 2.0 reactive wakeups.
  - **ADR-006 (Argument Rewrite Interception)**: Standardized on `PreToolUse` shallow `overwrite` dictionaries to sanitize benign pattern-matching pipelines (`|| true`), enforce non-interactive pagers (`PAGER=cat`), and inject network timeouts (`-o ConnectTimeout=5`).
* **Canonical Specifications Committed**:
  - [docs/official-specs/platform-surface-mapping.md](docs/official-specs/platform-surface-mapping.md): 655-line definitive deconstruction of CLI (`agy`), 2.0 Desktop Platform, Python SDK (`google-antigravity`), Lifecycle Hooks (`hooks.json`), and MCP boundaries mapped against the 348-session audit.

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
  - Hook Implementation: [harness/hooks/output_compactor_hook.py](harness/hooks/output_compactor_hook.py)
  - Test Suite: [tests/test_output_compactor.py](tests/test_output_compactor.py)
  - Hook Registry: [harness/hooks/hooks.json](harness/hooks/hooks.json)
  - Benchmark Report: [docs/taxonomy/output-compactor-poc-results.md](docs/taxonomy/output-compactor-poc-results.md)

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
  - Runtime Matrix: [harness/runtime/matrix.json](harness/runtime/matrix.json)
  - Workstation Doctor: [pipeline/psl_doctor.py](pipeline/psl_doctor.py)
  - Command Safety Hook: [harness/hooks/command_safety_hook.py](harness/hooks/command_safety_hook.py)

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
  - Unified CLI: [harness/cli.py](harness/cli.py)
  - Testing Contract: [docs/official-specs/testing-contracts.md](docs/official-specs/testing-contracts.md)
  - Test Suites: [tests/test_anti_loop.py](tests/test_anti_loop.py), [tests/test_cli.py](tests/test_cli.py)

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
  - Skills Engine: [harness/skills/__init__.py](harness/skills/__init__.py), [harness/skills/psl-stack-shell/SKILL.md](harness/skills/psl-stack-shell/SKILL.md), [harness/skills/psl-stack-typescript/SKILL.md](harness/skills/psl-stack-typescript/SKILL.md), [harness/skills/psl-stack-python/SKILL.md](harness/skills/psl-stack-python/SKILL.md), [harness/skills/psl-stack-backend/SKILL.md](harness/skills/psl-stack-backend/SKILL.md), [harness/skills/psl-stack-systems/SKILL.md](harness/skills/psl-stack-systems/SKILL.md)
  - Subagent Registry: [harness/subagents.py](harness/subagents.py), [harness/agents/harness_builder.md](harness/agents/harness_builder.md), [harness/agents/harness_reviewer.md](harness/agents/harness_reviewer.md), [harness/agents/harness_auditor.md](harness/agents/harness_auditor.md)
  - CLI Discovery: [harness/cli.py](harness/cli.py) (`psl skills`, `psl agents`)
  - Test Suites: [tests/test_skills.py](tests/test_skills.py), [tests/test_subagents.py](tests/test_subagents.py)



