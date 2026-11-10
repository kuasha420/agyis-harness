<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Changelog

All notable changes to the `agyis-harness` project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Features & Architecture
- feat(context): propagate dynamic maxContextTokens and fix hud.js epoch boundaries
- feat(cli): align checkpoint create/prune subcommands and add opt-in clean --dist
- feat(release): harden release-notes and add native Keep-a-Changelog engine
- feat(mcp): Resilient schema key normalization & aliasing in MCP gateway bridge (#103)
- feat(hooks): Transparent scratch promotion, 250-char threshold, and run_command argument sanitization (#101, #102, #104)
- feat(telemetry): systemd daemon health inspection in doctor and exponential jitter gateway backoff (#55)
- feat(gui): align context window bar with native Upc algorithm and exact inference usage metadata
- feat(gui): decouple in-situ HUD SPA into assets and resolve audit defect ledger
  - extracted 2,666-line client SPA into harness/gui/assets/hud.js loaded via importlib.resources
  - relocated transcript extraction into harness/telemetry/extractor.py resolving ADR-014 packaging breach
  - fixed subagent colon parsing for plugin namespaces (psl-agy-harness:builder)
  - hardened telemetry daemon with post-commit mtime cache, capacity limits, and WAL mode
  - removed hardcoded paths and guarded 32-bit PE header parsing in RE commands
  - fixed HUD token fallback calculation inflation and aligned hotkey toggle sync
- feat(arch): codify 4-pillar AFF gate, macro smell sensing, and PSL-INV-011
  - upgraded all 8 agent personas and dynamic archetype scaffold
  - elevated subagent router Stage 4 to macro architectural audit and git commit gate
  - added delta-aware macro smell sensing to code review and milestone handoff
  - codified PSL-INV-011 Universal Architectural Fitness Invariant across all rule files
- feat(aff): native architectural fitness function and macro governance engine
  - zero-dependency AST import boundary, cycle, and structural smell analyzer
  - registered agyis audit aff/macro/fitness CLI commands
  - integrated architectural fitness diagnostics into agyis doctor
  - 21 hermetic unit and contract tests in tests/test_architectural_fitness.py
- feat(gui): auto-focus latest epoch, step, and last 50-step page on toggle
  - Implement centralized syncToLatestState() helper in trajectory HUD template
  - Auto-select latest epoch (state.activeEpochIndex = epochs.length - 1) on toggle and load
  - Auto-select latest step (state.selectedIndex = steps.length - 1) on toggle and load
  - Auto-navigate tablePage to totalPages - 1 to display the latest 50 steps
  - Ensure style.display = "flex" runs before scrollIntoView() to prevent silent scroll no-ops
  - Wire syncToLatestState() into initial mount, ConnectRPC resolution, fallbacks, and hotkeys
  - Add comprehensive unit tests in tests/test_gui.py asserting order and state invariants
- feat(gui): granular context slices, native tool step unpacking, and checkpoint parity
  - Parse system prompt XML sections into 15 granular context bar slices
  - Partition tool definitions into Filesystem, Terminal, Subagents, and Automation slices
  - Unpack native ConnectRPC tool payloads: runCommand, viewFile, codeAction diffs, invokeSubagent, checkpoint
  - Render compaction milestone card with tokens reclaimed metric and epoch jump handler
  - Suppress TTFT/streaming bar on non-model steps (USER_INPUT, CHECKPOINT, SYSTEM)
  - Add unit tests in tests/test_gui.py asserting cleanroom parity and sub-second latency
- feat(gui): direct native ConnectRPC trajectory HUD and daemon deprecation
- feat(gui): dynamic 4-row context bar, checkpoint scoping, and prettified step inspector
- feat(gui): implement authoritative 256k context capacity, Atc dynamic sizing, and compaction summary parity
- feat(gui): implement dynamic trajectory server and codify PSL-INV-010 anti-vibe invariant
- feat(gui): upgrade in-situ trajectory debug HUD to 2.26.0 parity and add systemd CLI service manager
- feat(gui): reimplement in-situ trajectory debug HUD from reverse-engineered 2.24.0 architecture
- feat(plugin): add SVG plugin logo and register in plugin.json
- feat(upstream): support lastUserInput hook payload, teamwork slash command, colon agent variants, and print-timeout
- feat(doctor): context-aware forensic reverse-engineering & dirtyroom diagnostics (Fixes #100)
  - Add harness/runtime/re_checks.py with fast-path binary probes (<0.001s which, bounded 0.2s version extraction)
  - Implement is_re_workspace() auto-detecting .dirtyroom/ and docs/specs/ cleanroom policies
  - Support profile selection via dirtyroom.env (static-cleanroom vs dynamic-game-harness)
  - Audit Ghidra analyzeHeadless, OpenJDK 21+, objdump, REA patch (PSL-INV-009), dirtyroom.db, tshark, gpu-screen-recorder, ydotoold, xdotool
  - Integrate into run_doctor() and register --re flag on doctor CLI
  - Implement heal_forensic_toolchain() in harness/runtime/healing.py for zero-sudo REA patch & dirtyroom db auto-healing
  - Author comprehensive hermetic tests in tests/test_re_doctor.py (20 tests, sub-second benchmark)
- feat(re): add native disasm and xrefs subcommands to agyis re

### Bug Fixes & Hardening
- fix(gui): harden CDP target hydration, skip data URIs, and restore hotkey re-render
- fix(liveness): skip trailing ephemeral messages and classify terminal system messages as completed
- fix(quality-gates): decompose completion fence, harden liveness/cockpit, and clean ledger
- fix(gui): Trajectory HUD model fallbacks, multi-schema tokens, system previews, and syntax-highlighted JSON (#105)
- fix(gui): resolve double keydown cancelation on F12 and eliminate unbounded subagent pre-bundling slowness
- fix(telemetry): guard unique index deduplication in schema and use WAL connection factory in extractor
- fix(gui): correct cumulative context token accounting and resolve maximize titlebar clipping
- fix(gui): unify keydown listener, fix stylesheet order, and enable detached trajectory server
- fix(gui): eliminate template substitution token collision in trajectory HUD payload
- fix(telemetry): harvest local transcripts in daemon and prevent unbounded memory leak
- fix(hygiene): exclude .dirtyroom from node script hygiene audit and git tracking
- fix(upstream): remediate 24kb skill truncation, rule frontmatter validation, and cdp gui devtools
- fix(re): support legacy class_name/demangled_name schema and integer addresses in cmd_find

### Documentation & Usability
- docs(changelog): update Unreleased entries with liveness fix
- docs(changelog): update Unreleased entries for RC10 preparation

### Maintenance & Release
- build(release): harden release CI workflow, packaging assets, and uv lockfile

---

## [1.0.0-rc9] - 2026-11-03

### Features & Architecture
- feat(re,ext,cockpit): bump to v1.0.0-rc9 with cleanroom RE toolsuite, CLI extensions, and token harmonization

### Bug Fixes & Hardening
- fix(agents): mandate native REA tooling and ban ad-hoc python disassemblers in agyis_investigator
  - Codify Tool-Native Reverse Engineering Invariant (PSL-INV-004 §3) in agyis_investigator
  - Enforce native REA CLI and MCP commands for binary reverse engineering (ELF, PE, Mach-O)
  - Strictly prohibit hand-rolled Python binary parsers, offset scrapers, and ad-hoc disassemblers
  - Add validation gate in harness/subagents/validator.py requiring investigator prompts to declare REA invariant
  - Scaffold investigator agents with REA invariant in harness/subagents/scaffold.py
  - Fix test_compaction_checkpoint isolation to avoid host environment leakage

---

## [1.0.0-rc8] - 2026-10-28

### Features & Architecture
- feat(hygiene): codify universal gitignore & exclude patterns for cockpit, router & agent artifacts
- feat(subagents): Dynamic MCP Tool Scoping & Multi-Line Shell Script Hygiene Hook (#97)
- feat(cleanroom): native REA integration, runtime healing, and typed obligation schemas (#96)
  - Node semver compatibility ladder & pnpm user-space auto-healing
  - JDK 21+ discovery ladder & zero empty-string JAVA_HOME guarantee
  - Non-interactive rea setup --yes safety injection
  - Strict REA 6.8.0 typed obligation schemas and completion fence integration
  - agyis verify --scaffold and REA 6.8.0 CLI delegation
  - Hermetic sub-second test suite (tests/test_rea_cleanroom.py)

### Documentation & Usability
- docs(taxonomy): record Phase 32 completion in project ledger (#97)
- docs(ledger): record Phase 31 completion in project ledger (#96)

### Maintenance & Release
- chore(release): bump version to v1.0.0-rc8 and record Phase 33 in project ledger
- chore(hygiene): purge root operational artifacts, test documents, and prompt handovers (AC5)
- test(command-safety): update replay test for PSL-INV-002 §4 inline script hygiene (#97)

---

## [1.0.0-rc7] - 2026-10-27

### Features & Architecture
- feat(telemetry): real-time attention horizon & token burn rate velocity gauges (Issue #68)
- feat(cli): holistic active conversation detection and subagent scoping (#95)
  - Centralized context engine (harness/utils/context.py) resolving ANTIGRAVITY_CONVERSATION_ID, ANTIGRAVITY_SOURCE_METADATA, and ANTIGRAVITY_BRAIN_DIR
  - Scoped subagent liveness and 24h expiration TTL on PARKED_STATE.md resolving the global pause trap
  - CLI flags --all / -a and --session for subagents command
  - Auto-defaulting active conversation in checkpoint and cockpit commands
  - Comprehensive unit test coverage and <0.05s SLA benchmark
- feat(subagents): dual-gate out-of-band auditor verification fence (Issue #66)
  - Implements Gate 2 (Out-of-band Auditor Verification Fence) in completion_fence_hook.py.
  - Adds AuditVerdict dataclass, validate_audit_verdict(), and generate_audit_verdict() in harness/subagents/verdict.py.
  - Implements agyis audit certify and agyis audit verdict CLI commands.
  - Implements Role Fencing Matrix (Solo bypass, Worker exempt, Coordinator strict Gate 2 with 2-block anti-deadlock safety valve).
  - Updates auditor agent personas and explicit command dictionaries.
  - Adds unit tests in tests/test_audit_verdict.py and tests/test_completion_fence_hook.py.
- feat(subagents): operationalize persona truth enforcement & anti-code-monkey invariant (#72)
- feat(subagents): implement delegate liveness CLI and cognitive wiring (Issue #78 / Epic #74)
- feat(resilience): implement zero-kill pause gate and powerloss disaster recovery (#65, #76, #75)
  - Expand command safety hook matcher in hooks.json for run_command, manage_task, and manage_subagents.
  - Implement check_pause_safety and is_pause_gate_active in command_safety_hook.py to intercept and block destructive terminations (kill, kill_all, cancel, kill -9) when pause gate is active.
  - Author graceful-parking skill with bilateral handshake, PARK_ACK tokens, state serialization, and non-destructive parking.
  - Author powerloss-resume skill with 5-phase crash recovery (status probe, lock recovery, git triage, daemon check, test verification) avoiding destructive git resets/clean.
  - Register 'resilience' and 'continuity' presets in GROUP_PRESETS in harness/skills/__init__.py.
  - Add comprehensive hermetic unit tests covering zero-kill safety guards, pause gate parsing, and resilience skills discovery/presets.
- feat(rules): implement single-source rule deduplication engine & canonical invariant anchors (#70, #71)
  - Codified 8 Canonical Invariants (PSL-INV-001 through PSL-INV-008)
  - Implemented enforce_single_source_rules() and lint_rule_echo() in harness/delivery/surfaces.py
  - Added agyis rules CLI command with --dedup and --lint
  - Integrated rule deduplication into agyis onboard (step 12b)
  - Pruned redundant universal sections from workspace rules (~1,630 tokens/turn saved)
  - Anchored agent personas to cite canonical invariant identifiers
  - Added hermetic unit tests in tests/test_rule_bifurcation_and_packaging.py
- feat(telemetry): database compaction & historical raw argument pruning policy (#56)
- feat(hygiene): agent & cockpit file management hygiene, checkpoint retention & subagent telemetry bridge (#90)
- feat(skills): dedup subagent-ladder via skills import and symlink agent skills (#92)
- feat(skills): codify 'cockpit-director' & dynamic 'subagent-router' with flight director CLI tooling (#92)
- feat(subagents): implement horizontal succession protocol and self alias ladder (#77)
- feat(hooks): automate pre-compaction serialization trigger at 230k tokens (#77)
- feat(cli): add agyis checkpoint command palette (#77)
- feat(delivery): productize carrier-grade compaction checkpoint serializer (#77)
- feat(subagent-ladder): implement stage-aware sequential heartbeat crons and telemetry (#84)
- feat(subagent-ladder): enforce thrashing-activated dynamic horizon fence during remedy turns (#86)
- feat(subagent-ladder): codify full-pipeline role-pinning prompts across ladder stages (#85)
- feat(agents): harmonize test suite, anti-drift investigator guard, and cli references (#87)
- feat(subagent-ladder): harmonize skill runbook with 12-workflow routing and investigation branch (#87)
- feat(agents): rename specialist agents to agyis_* prefix, introduce agyis_investigator and alias bridge (#87)
- feat(hooks): expand role normalization engine for agyis specialist fleet (#87)
- feat(hooks): carrier-grade hardening against adversarial concurrency, schema fuzzing, token bursts, and binary noise (#83)
- feat(hooks): implement 3-pillar dynamic monolith classifier and cognitive state flush (#83)
- feat(hooks): codify compaction advisory runner aliases, custodian role, and dynamic runway (Issue #83)
- feat(hooks): implement universal 230k-token compaction advisory via PreInvocation hook (#83)
- feat(epic-51): synthesize phase 3.1 golden merge candidate with rigorous anti-synthetic verification
- feat(safety-net): synthesize Phase 3.1 golden merge candidate (Epic #51)
- feat(testing): implement Epic #51 Phase 1 & 2 (P0 fence triad, diff-aware runner, psl-test-harmonize)
  - Repair living telemetry DB scalar coupling in tests/test_audit_report.py
  - Implement Diff-Aware Affected Testing Architecture in agyis test (--diff, --affected, --pkg, --full)
  - Add 3-tiered dependency resolver (native -> structural heuristic -> directory/package)
  - Author psl-test-harmonize runtime skill & agyis harmonize test with safe backup patches
  - Integrate tier-gated completion fence state (test:diff for turns, test:affected for handoffs)
  - Verified with 1,198 project tests and out-of-band Victory Auditor certification

### Bug Fixes & Hardening
- fix(plan_parser): ignore *.metadata.json companion artifacts in plan discovery (#94)
- fix(checkpoint): prevent stale plan hijacking in find_active_plan & compaction engine (#94)
- fix(skills): declare Workspace share in subagent-ladder import shim (#92)
- fix(hooks): bypass native system slash commands in PreInvocation to prevent interceptor collisions (#83)
- fix(tests): decouple test_audit_report scalar checks from post-fleet-sync telemetry.db growth
- fix(hooks): resolve TTL lock wipe, permission error abort, and CIFS/EMFILE caching (#83)
- fix(hooks): harden route c against cid suffix, permission denial, token lag, and nfs lock edge cases (#83)
- fix(hooks): resolve TTY hang, timeout clamping, TTL locked IDs, and SQLite connection leaks (#83)
- fix(hooks): Fix PreInvocation fail-open schema in runner.py and anchor step_type query in token_proximity_guard (#82)
- fix(hooks): resolve PreToolUse classification deadlock and Stop fence cockpit friction
  - Eliminate tool_name in ('run_command', ...) from is_post_tool_use detection, preventing fail-closed pre-tool execution rejections
  - Add orchestrator, cockpit, flight director, and main agent role exemptions to evaluate_stop
  - Reconcile empty last_modified_files with git status truth-anchor to eliminate phantom untracked code files blocks
  - Realign contract test assertions for pre-tool run_command allow decisions
  - Add regression unit tests for orchestrator role exemption and git truth-anchor
- fix(tests): decouple test_async_background_tier_gating from wall-clock timestamp drift
- fix(telemetry): use INSERT OR IGNORE in extract and harvest pipelines for composite unique constraints

### Documentation & Usability
- docs(taxonomy): record phase 29 completion in project ledger (Issue #68)
- docs(taxonomy): record Phase 28 active conversation detection and subagent scoping (#95)
- docs(taxonomy): record phase 27 dual-gate auditor verification fence in project ledger
- docs(taxonomy): record Phase 26 project ledger entry (#94)
- docs(taxonomy): record phase 25 completion in project ledger (#72)
- docs(ledger): record Phase 24 completion and Epic #74 final closure
- docs(ledger): preserve Phases 1-20 and append Phases 21, 22, and 23
- docs(ledger): record Phase 22 completion for swarm continuity and disaster recovery (#65, #76, #75)
- docs(ledger): record Phase 21 (Issues #70, #71) and Phase 22 (Issue #56) completions
- docs(ledger): record Phase 20 completion for Issue #92 and Issue #90
- docs(research): publish canonical research papers on multi-agent systems, hook contracts, and cognition boundaries
- docs(ledger): close out epic 51, record phase 18 completion and phase 19 adr-031 succession
- docs(architecture): codify cockpit flight director operational living contract (#87)
- docs(ledger): compact Phase 18 Epic #51 milestone progress
- docs(telemetry): refresh empirical audit taxonomy reports across 1,720 sessions

### Maintenance & Release
- chore(release): harmonize manifests and documentation for v1.0.0-rc7 release
- chore(research): sanitize local paths, conversation UUIDs, and binary characters in docs/research
- test(subagent-ladder): add end-to-end integration test suite for ladder triad (#51)
- refactor(hooks): sanitize compaction advisory directives from flush to persist (#87)
- refactor(subagent-ladder): decouple skill and specialist agents into domain-agnostic SWE primitives (#87)

---

## [1.0.0-rc6] - 2026-10-18

### Features & Architecture
- feat(release): automated conventional release notes generator and v1.0.0-rc6 harmonization

### Documentation & Usability
- docs: streamline README with 5-minute happy path and onboard engine

---

## [1.0.0-rc5] - 2026-10-18

### Features & Architecture
- feat(cli): unified agyis onboard CLI engine completion (#58)
  - Add CLI flags --allow-dirty, --create-branch, --purge-caches, --no-cache-purge
  - Implement dirty working tree safety gate aborting unless --allow-dirty
  - Export pre-onboard safety patch to .agents/artifacts/wip-safety-pre-onboard.patch
  - Implement dedicated branch isolation and checkout ladder
  - Wire cache invalidation and database port conflict warnings for backend/fullstack roles
  - Add 7 hermetic unit tests in tests/test_onboard.py
- feat(skills): dynamic database port collision detection in db-ops and doctor (#62)
  - Add standalone detect_port_collision.py script using Python standard library only
  - Implement 3-tier collision ladder: socket probe, Docker attribution, free port scan (5432-5442), regex-safe .env re-binding
  - Add check_database_port_conflicts in hygiene_checks.py and wire into agyis doctor
  - Add db-ops runbooks in SKILL.md (§§4.4-4.6)
  - Add 33 hermetic unit tests in tests/test_db_ops_skill.py
- feat(delivery): standalone automated build cache invalidation module (#63)
  - Extract purge_workspace_build_caches into harness/delivery/cache.py
  - Enforce strict workspace path containment and symlink safety
  - Target .next, .turbo, and node_modules/.cache up to depth 3
  - Add 19 hermetic unit tests in tests/test_cache_invalidation.py
- feat(gui): add --no-popup flag to prime shortcuts and command palette without auto-opening modal
- feat(gui): Seamless Trajectory Debug View unlocking and autonomous persistence
  - Bare CLI Default: Executing 'agyis gui' without action flags defaults directly to unlocking Trajectory Debug View.
  - Toggle Control: Added '--toggle' flag to flip Trajectory Debug View open/closed state via URL searchParams and PopStateEvent.
  - Startup Readiness Polling: Added '--wait <seconds>' option to poll DevToolsActivePort and skip 'about:blank' until the active webview loads.
  - In-Window Hotkey Listener: Injected DOM keydown listener for F12 and Ctrl+Shift+T, persisted across reloads via Page.addScriptToEvaluateOnNewDocument.
  - Standalone CLI Alias: Provisioned instant user executable '~/.local/bin/agy-debug' forwarding to 'agyis gui'.
  - Autonomous Kernel-Level Persistence: Configured systemd user path and service units watching DevToolsActivePort to trigger unlocking on app launch.
  - Hermetic Verification: Added comprehensive unit tests in tests/test_gui.py covering bare defaults, toggle routing, wait polling, and hotkey registration.
- feat(agents): Horizon 1.6 Agent Architecture Overhaul & REA GUI Telemetry
  - Subagents Engine (R1): Universal send_message across all capability bundles
  - Persona Alignment (R2): Codify native Antigravity primitives (/teamwork-preview,
  - REA GUI Telemetry (R3): Zero-dependency stdlib RFC 6455 WebSocket client for
  - Token Proximity Guard (R4): Fail-open PreToolUse lifecycle hook with dynamic
  - Verification (R5): 988 tests passing in ~15s, 100% Python standard library
  - Certified via Triple Auditor Gate (In-Band Council, Delta Re-Audit, Clean-Room Blind Audit).
- feat(release): v1.0.0-rc5 Phase 1 remediations, fleet harmonization & REA GUI telemetry

### Bug Fixes & Hardening
- fix(tests): accommodate CI runner scheduling jitter in doctor fast-path latency benchmark
- fix(tests): hermetic isolation for sparse PATH and minimal environments in doctor REA tests
- fix(tests): hermetic isolation for CI runner environment in doctor and REA tests
- fix(gui): retry through unhydrated origin SecurityError during startup wait polling
- fix(hooks): clear spec_dirty upon successful agyis verify --spec execution

### Documentation & Usability
- docs(release): commit v1.0.0-rc5 release preparation bundle and fleet audit reports
- docs: compact Phase 13 findings into project ledger and roadmap
- docs(specs): commit REA reverse engineering deliverables, deep dive, and turnkey succession specification
- docs(release): master successor handoff specification & roadmap update for v1.0.0-rc5 overhaul
- docs(handoff): compact Phase 11 v1.0.0-rc4 in ledger, update roadmap, and author rc5 starter prompt

### Maintenance & Release
- chore(release): bump version to 1.0.0-rc5
- release: prepare v1.0.0-rc5 documentation hydration, test noise suppression, and strategic fleet alignment

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

[Unreleased]: https://github.com/kuasha420/agyis-harness/compare/v1.0.0-rc9...HEAD
[1.0.0-rc9]: https://github.com/kuasha420/agyis-harness/compare/v1.0.0-rc8...v1.0.0-rc9
[1.0.0-rc8]: https://github.com/kuasha420/agyis-harness/compare/v1.0.0-rc7...v1.0.0-rc8
[1.0.0-rc7]: https://github.com/kuasha420/agyis-harness/compare/v1.0.0-rc6...v1.0.0-rc7
[1.0.0-rc6]: https://github.com/kuasha420/agyis-harness/compare/v1.0.0-rc5...v1.0.0-rc6
[1.0.0-rc5]: https://github.com/kuasha420/agyis-harness/compare/v1.0.0-rc4...v1.0.0-rc5
[1.0.0-rc4]: https://github.com/kuasha420/agyis-harness/compare/v1.0.0-rc3...v1.0.0-rc4
[1.0.0-rc3]: https://github.com/kuasha420/agyis-harness/compare/v1.0.0-rc2...v1.0.0-rc3
[1.0.0-rc2]: https://github.com/kuasha420/agyis-harness/compare/v1.0.0-rc1...v1.0.0-rc2
[1.0.0-rc1]: https://github.com/kuasha420/agyis-harness/compare/v1.0.0-rc0...v1.0.0-rc1
[1.0.0-rc0]: https://github.com/kuasha420/agyis-harness/commits/v1.0.0-rc0
