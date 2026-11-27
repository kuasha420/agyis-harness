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

*No changes.*

---

## [1.1.1] - 2026-11-27

### Features & Architecture
- feat(release,ci,docs): add unified agyis release bump/check CLI, sync-check uplift & SSOT convergence
- feat(skills): add paired /pause and /resume skills with live-first 3-branch triage
- feat(hooks): add anti-clobber guard (#93), memory/concurrency semaphore (#67), scaled horizon & subagent stop-gate truth

---

## [1.1.0] - 2026-11-27

### Features & Architecture
- feat(telemetry,audit): add Gate 0 DB integrity repair & deduplication (`harness/telemetry/integrity.py`, `integrity_dedup.py`), sync watermarks, keyset cursor pagination, sibling DB & protobuf models, Git Era x Model analyzer (`pipeline/analyze_eras.py`), privacy-safe website exporter (`pipeline/export_website_metrics.py`), and explicit local-corpus provenance disclosures across the `3,856`-session (`2026-05-24`–`2026-11-25`) Gate 0 telemetry baseline (Wave 1.1 / G0.1)
- feat(re,cli): promote stable `--rea` flag alongside `--re` (`doctor --re` / `--rea`), add `agyis clean --caches`, wire `agyis onboard` verification gates (`harness/commands/onboard_gates.py`), and harden background sync watch/service lifecycle (Wave 1.1)
- feat(hooks,subagents,aff): add Antigravity `v2.35.2` strict `exa.hooks_pb` wire compatibility (`harness/hooks/wire_compat.py`), SQLite lineage role pinning (`harness/hooks/role_lineage.py`, `harness/trajectory/lineage.py`), `19` `CANONICAL_PLATFORM_TOOLS` + `2` `ROOT_PLAN_MODE_TOOLS` (`30` total `ANTIGRAVITY_PLATFORM_TOOLS`) registry, MCP argument normalization (`harness/hooks/mcp_normalizer.py`), split AFF checks (`harness/runtime/aff.py`, `aff_extract.py`) with bounded JS cache enforcement, and `agyis audit sync-check [--include-site]` (`harness/delivery/sync_check.py`) (Wave 1.2)
- feat(theme,gui): launch Orbital Aegis cross-surface CLI theme (`harness/utils/theme.py`), `v2.35.2` hooks UI parity, `:40624` playback shell (`playback_boot.js`, `playback_shell.html`, `trajectory_catalog.py`), and modular `hud_stream.js` & `hud_utils.js` assets loaded via `importlib.resources` (Wave 1.3–1.4)
- feat(cli,subagents): optimize `agyis` CLI startup with PEP 562 lazy command imports (`harness/cli.py`, `harness/commands/__init__.py`) and bound `agyis subagents --liveness` transcript tail reads to `64KB` (Wave 1.4)

### Bug Fixes & Hardening
- fix(gui,hud): stabilize live ConnectRPC Trajectory HUD `CHECKPOINT` selection via Option-B disjoint checkpoint window partitioning (`0..c0-1`, `c_k..c_{k+1}-1`), `resolveCheckpointForStep` reverse-scan preservation, unified search/filter/scroll/focus snapshots, `__agyis_context_bar` `v2.35.2` global namespace isolation, and `:40624` playback parity (Wave 1.3–1.4)
- refactor(checkpoint): standardize trajectory, hook, subagent, rule, skill, agent, documentation, and landing-page terminology from `epoch` to `checkpoint` (`SOFT_CHECKPOINT_STEP_ADVISORY = 80`, `[AGYIS CHECKPOINT HORIZON ADVISORY]`, `[CHECKPOINT HORIZON]`, `checkpoints` / `checkpoint_index` / `checkpoint_steps`, and `compaction_checkpoint_<ts>.md`), preserving Unix wall-clock timestamps and historical backwards-compatibility read fallbacks (Wave 1.4)
- fix(telemetry): harden `agyis-sync.service` against deleted/transient CWD `[Errno 2]` errors (`_is_transient_dir`), add slim transcript step projection (`_project_transcript_step`) & bounded cache/RSS trimming (`_trim_process_memory`, `_seed_mtime_cache`), auto `try_restart_service` on global install, and report `daemon_version` drift in `agyis doctor` (`check_telemetry_daemon`) (Wave 2.6, `#121`)
- fix(delivery): harden `DeliveryMode.COPY` with symlink-safe removal (`_remove_existing_path`) and prune stale `dist/` / `*.dist-info/` artifacts in `harness/delivery/copy_install.py` (Wave 2.6, `#119`)
- fix(test,launcher): resolve local CWD repository checkouts in global `agyis test` (`_delegate_to_cwd_checkout`) and prefer repo `.venv/bin/python` in `harness/commands/test.py` and `harness/delivery/bin_launcher.py` (Wave 2.6, `#120`)

### Documentation & Website
- feat(website,ci): expand Orbital Aegis GitHub Pages showcase to 5 routes (`index`, `telemetry`, `cognitive`, `hud-re`, `brand`), publish 6 PII-audited Gate 0 telemetry JSON bundles (`website/data/`) with `1200x900` studio PNG/WebP artwork, split `.github/workflows/pages.yml` into race-free build/deploy jobs, and update `og-image` for `v1.1.0` (Wave 2 & Wave 3)
- feat(website): implement zero-FOUC unified Light/Dark design system (`light-dark()`, WCAG AA `--accent-solid` controls, polarity-adaptive SVG chart tokens), `2.5D` surface elevation & pointer/scroll motion under `prefers-reduced-motion`, and responsive QA across all 5 routes (Wave 2.5)
- docs(release): reconcile `README.md` (with empirical corpus provenance disclosure), `roadmap.md`, `CHANGELOG.md`, `docs/taxonomy/project-ledger.md` (`<50` lines), user/developer guides, official specs, runbooks, ADR registry, and GitHub issue templates for `v1.1.0` (`2,572` hermetic tests across `119` modules) (Wave 3)

---

## [1.0.0] - 2026-11-25

### Features & Architecture
- feat(codex-v2): adopt **PSL Invariant Codex v2** (`PSL-INV-001`–`008` core invariants + on-demand `PSL-RE-001` cleanroom RE domain pack in `re-ops`), deduplicate `GLOBAL_AGENTS.md` / `harness/rules/*` / `.agents/rules/AGENTS.md`, and symlink `.agents/agents/*` cleanly
- feat(agents,gemini-4): enforce the `<=20` canonical `v2.34+` tool ceiling (`CANONICAL_PLATFORM_TOOLS`) across `harness/subagents/{spec,validator}.py` and all 8 `agyis_*.md` personas, and align context runway docs and health models for **Gemini 4 (`gemini-4-neon`, `gemini-4-hydrogen`, `512k`/`1M`)** and `agy v1.5.15`
- feat(delivery,re,gui): migrate `install_workspace()` completely onto the decoupled language + role resolver, harden `harness/gui/server.py` (traversal guard, cache lock, `ANTIGRAVITY_APP_DATA_DIR`), `harness/telemetry/{config,client,db}.py`, `harness/re/*` (`ELF`/`PE`, `GhidraReleasePolicy`, daemon cleanup, SQLite schema), and `harness/cleanroom/obligation.py` strict `rea@6.9.0` schema

### Bug Fixes & Hardening
- fix(hooks,cli): remediate Slice 1–3 audit findings across `command_safety_hook.py`, `anti_loop_hook.py`, `output_compactor_hook.py`, `completion_fence_hook.py`, `anti_drift_hook.py`, `runner.py`, `audit certify` (`audit_architectural_fitness` + real test execution), `enforce_single_source_rules`, and `cmd_test` project runner routing
- test(hermetic,aff): pass `2,441` hermetic tests across `108` modules in `~24s` (`0` anti-synthetic hard rejections), reach `100.0/100` AFF in `~0.035s` with `audit.py` exemption removed, and sanitize/elevate `scripts/`, `pipeline/`, and `PROJECT.md`
- docs(launch): reconcile `README.md`, `roadmap.md`, `docs/user_guide.md`, `docs/developer_guide.md`, `docs/adr/README.md`, compacted `docs/taxonomy/project-ledger.md` (`<50` lines), all `7` `docs/official-specs/*`, `4` `docs/runbooks/*`, `4` `docs/specs/*`, `TEST_INFRA.md`, and `TEST_READY.md` for `v1.0.0` GA public launch

---

## [1.0.0-rc14] - 2026-11-23

### CI, Packaging & Documentation
- ci(release): synchronize `uv.lock` with `pyproject.toml`, replace stale bare `verify` gate in `.github/workflows/release.yml` with `agents validate --json`, and restore automated wheel (`.whl`) and source distribution (`.tar.gz`) release artifact publication
- ci(workflow): add continuous `.github/workflows/ci.yml` (`push` to `main`, `pull_request`, `workflow_dispatch`) with full git history/tags (`fetch-depth: 0`, `fetch-tags: true`), lockfile check, symlink & cleanroom spec checks, schema/AFF gates, full hermetic test suite, and isolated wheel smoke test
- test(packaging): add `test_uv_lock_matches_pyproject_version` and `test_ci_workflow_present_and_hardened` in `tests/test_rule_bifurcation_and_packaging.py` to prevent future lockfile or CI contract drift
- docs(entrypoints): refresh `README.md`, `roadmap.md`, `docs/user_guide.md`, `docs/developer_guide.md`, and `docs/taxonomy/project-ledger.md` for Gemini 4 (`512k`/`1M`), Antigravity `v2.34.0` compatibility, live CI badge, and `v1.0.0-rc14` release packaging

---

## [1.0.0-rc13] - 2026-11-23

### Features & Architecture
- feat(hooks): complete Antigravity `v2.34.0` lifecycle hooks compatibility across all remaining Stream 2 drifts (`DRIFT-P0-02`, `DRIFT-P0-03`, `DRIFT-P1-08`, `DRIFT-P2-01`, `DRIFT-P2-02`, closing Epic `#118` — **29/29 verified drifts resolved**):
  - Expand `harness/hooks/hooks.json` matchers (preserving root `hooks.json` symlink) and PreToolUse extractors for canonical `v2.34.0` tools (`write_file`, `edit_file`, `read_file`, `swarm`, `run_workflow`, `call_mcp_tool`, `mcp_.*`) and uppercase `Path`/`Content`/`Replacement` argument keys
  - Implement Q5 read-only shell mutation guard (`_is_mutating_shell_command`) in `anti_drift_hook.py` with indexed quote masking and path-traversal rejection for read-only/planning/review roles while allowing safe quoted reads, `agyis_investigator` `scratch/` writes, and `agyis_custodian` git commits
  - Normalize eager `mcp_*` tools to flat argument overwrites and guard `swarm{action:"kill"}` during pause gates in `command_safety_hook.py`
  - Support `hookEventName`, `payload["error"]`, nested dict `error`/`isError`/`status` detection, and omitted-exit-code success in `runner.py`, `completion_fence_hook.py`, `fence_classifiers.py`, and `fence_tasks.py`; narrow REA 6.8/6.9 ledger dispositions to `("active", "out-of-scope")`
  - Wire `PostToolUse` `{"overwriteResult": compacted}` in `output_compactor_hook.py` for `>2KB` succeeding `run_command` and `>32KB` `read_file`/`view_file` calls while preserving failing outputs and `<=32KB` reads 100% verbatim
  - Fix `_velocity_from_telemetry_db` in `token_proximity_guard.py` against live `telemetry.db` schema (`steps.content_length + thinking_length` and `sessions.file_size_bytes`)
  - Migrate all `pre_invocation_hook.py` advisories from deprecated `ephemeralMessage` to nested `systemMessage.systemMessage` (`0` hits in `harness/`), honor `StopHookArgs.continuationActive` in `fence_gates.py`, and support `ANTIGRAVITY_APP_DATA_DIR` in `fence_state.py` & `role_pinning.py`
- test(hooks): add dedicated hermetic regression suite `tests/test_hooks_v2_34_compat.py` and migrate all 5 pre-invocation test suites to `systemMessage`

---

## [1.0.0-rc12] - 2026-11-22

### Features & Architecture
- feat(gui,re,verify): Antigravity `v2.34.0` & `rea@6.9.0` compatibility across CDP/HUD/RE/cleanroom (`DRIFT-P0-06`, `P1-11..13`, `P2-05`, `P3-02`):
  - Add live Antigravity PID `--remote-debugging-port` diagnostics and opt-in `agyis gui --install-launcher` (`harness/gui/launcher.py`)
  - Upgrade `hud_rpc.js` / `hotkey.js` / `hud.js` for `agy_session_csrf_token` fallback, `trajectoryVerbosity: 3`, singular `executorMetadata`, `TokenType 8–10`, `CortexStepType.GENERIC (132)`, split routes `/c/<id1>+<id2>?focused=<id2>`, and DOM remount
  - Add Linux ELF64/ELF32 section/VA/RVA/offset & `objdump -T/-t` support in `agyis re addr/xrefs/preanalyze` and align `ReviewedObligation` / `verify` with `rea@6.9.0`
- feat(subagents,cockpit,skills): migrate `ANTIGRAVITY_PLATFORM_TOOLS`, `validator.py`, `scaffold.py`, and all 8 `agyis_*.md` agents to canonical `v2.34.0` tools (`read_file`, `write_file`, `edit_file`, `swarm`, `run_workflow`, `finish`, granting `run_command` to `agyis_reviewer`/`planner`/`coordinator`), `/swarm` liveness & rehydration, and CID-scoped `cockpit verify` (`DRIFT-P0-04`, `P1-01`, `P1-02`, `P1-05`, `P1-14`, `P2-03`, `P3-03`)
- feat(trajectory): fix `ModelUsageStats` `thought`/`output` field swap, add `TokenType 8–10` & recursive `TokenGroup`, handle `step_type` `132`/`101` & `fn=29` `modified_tool_call`, add `flock` `presence/*.lock` & `/swarm` lineage, `transcript_full.jsonl` & `args.Path` parsing, `ANTIGRAVITY_APP_DATA_DIR` (`agy` CLI), `512k`/`1M` Gemini model windows, and decouple `sync.py` from `pipeline/*` (`DRIFT-P1-02..07`, `P1-14`, `P2-01`, `P2-06`)

### Bug Fixes & Hardening
- fix(delivery,clean,onboard,doctor,rules): isolate `PluginInstaller` `config_dir`/`surfaces` & hermetic `test_delivery.py` (`DRIFT-P0-01`); guard `agyis clean` against active/dirty worktrees and scan `.agents/artifacts/checkpoints/` (`DRIFT-P0-05`); deduplicate `GLOBAL_AGENTS.md` in `copy_install.py` & modernize coexistence/surface sync (`DRIFT-P1-09`); gate `onboard --dry-run` against `gh repo fork`, fix skill pruning, and prevent `.agents/commands/*` shadowing core CLI subcommands (`DRIFT-P1-10`); wire real `doctor --heal` checks (`DRIFT-P2-04`) and clean `plugin.json` (`DRIFT-P3-01`)
- fix(re): implement PE32/PE32+ & ELF address inspection (`agyis re addr`), dual-mode cross-references (`agyis re xrefs`), smart procedure resolution (`agyis re decompile`), and hermetic test isolation

---

## [1.0.0-rc11] - 2026-11-15

### Features & Architecture
- feat(remote): decouple Knot Mesh specifics to gh:kuasha420/knot-mesh
  - Extract mesh-ops skill to gh:kuasha420/knot-mesh (runtime/skills/mesh-ops)
  - Extract display_bridge.py / screens subcommand to knot-mesh display carousel
  - Generalize drift_validators.py to accept agyis status and agyis remote triage as telemetry proofs
  - Decouple skills presets and update test suites (2,354 tests passing, 100.0/100 AFF score)
- feat(onboarding, gui): implement bug bash Q1 real-project onboarding, harmonization decoupling, and Q4 HUD streaming enhancements
- feat(gui): integrate cleanroom modular trajectory HUD with live ConnectRPC streaming and subagent traversal
- feat(onboard,harmonize): support non-monorepo polyglot projects (Issue #106)
- feat(telemetry): decouple cleanroom session extractor, lag health diagnostics, and audit upsert
- feat(trajectory): consolidate trajectory reader, protobuf decoder, context health & checkpoint succession onto SSOT
- feat(hygiene): enforce in-tree skill symlink deduplication gate

### Bug Fixes & Hardening
- fix(test): enable stdio buffering by default to eliminate negative assertion noise
- fix(remote): swallow service probe errors, export parsed sections, and cd to staged dir (DEF-BB-055..057)
  - DEF-BB-055: Add error swallowing to docker ps and pm2 service probes with trailing true guarantee in build_triage_probe
  - DEF-BB-056: Extract parse_sections and return parsed sections dict in run_triage for structured JSON consumption
  - DEF-BB-057: Prepend cd to temporary staged directory in stage_script to isolate script working directory and prevent scratch leakage
  - Add regression tests in tests/test_remote_runner.py (all 20 passing hermetically)
- fix(remediation): trim trajectory_hud to <=790 lines, restore hud_rpc while loop, and mount genuine production code in phase 2 tests
- fix(remote): remediate Frontier 2 defects DEF-BB-047 through DEF-BB-051
- fix(gui): remediate Frontier 1 defects DEF-BB-041 through DEF-BB-046
- fix(hooks,telemetry): remediate adversarial fuzzing & WAL concurrency defects (DEF-BB-028..035, DEF-BB-052..054)
- fix(cleanroom,re): remediate REA 6.8.0 schema drift, Ghidra SLA, and CLI delegations (DEF-BB-036..040)
  - DEF-BB-036: Align cleanroom obligation ledger schema with REA 6.8.0:
    - Disallow top-level $schema (deprecated in REA 6.8.0)
    - Extend EvidenceBundle with captures, environments, scenarios, unknowns
    - Require manifest.bindings as list of dicts instead of dict
    - Validate reviewed_obligations disposition enum (active, blocked, out-of-scope)
    - Update scaffolded obligation ledger template accordingly
  - DEF-BB-037: Enforce PSL-INV-009 §1 & §2 Ghidra SLA benchmarks:
    - Prohibit decompilation of binaries >10MB without prior headless Ghidra pre-analysis
    - Enforce 15.0s timeout SLA on decompiler executions to detect cache bypass
  - DEF-BB-038: Standardize CLI command aliases and fix Ghidra path compatibility:
    - Support 'preanalyze' alias alongside 'pre-analyze' in 'agyis re'
    - Create non-dot symlink alias (dirtyroom) to circumvent Ghidra ProjectLocator '.' rejection
    - Point REA_GHIDRA_PROJECT_DIR to non-dot path
  - DEF-BB-039: Streamline REA delegation in verify CLI:
    - Delegate to 'rea build-reconstruction-obligation-ledger' with 30s timeout
    - Fall back cleanly to native cleanroom verification on missing CLI or timeout
    - Update fence classifiers for active and out-of-scope obligation dispositions
  - DEF-BB-040: Detect Ghidra 12.2 and inject OpenJDK 27:
    - Add is_ghidra_12_2_installed detector scanning standard install locations
    - Prefer /usr/lib/jvm/java-27-openjdk when Ghidra 12.2 is detected
    - Patch REA GhidraReleasePolicy.js for Ghidra 12.2 compatibility
- fix(harness): resolve bug bash defects across CLI palette, lifecycle hooks, and REA cache
  - DEF-BB-004: Add --json flag support to agyis status CLI with structured telemetry, hooks, and token metrics.
  - DEF-BB-005: Detect general python3 script invocations in command safety hook to inject hermetic uv CPython >= 3.12.
  - DEF-BB-013: Neutralize interactive systemd pagers (systemctl, journalctl, udevadm) via SYSTEMD_PAGER=cat.
  - DEF-BB-014: Block destructive rm on home directories (~, $HOME) and destructive git commands (reset --hard, checkout -- ., clean -fd).
  - DEF-BB-015: Add test_output_compactor_hook.py alias suite for pattern discovery.
  - DEF-BB-016: Expand mnemonic routing aliases for 'fix' (Route A), 'discovery' (Route G), and 'custodian' (Route K).
  - DEF-BB-017: Expand subagent role resolution keys in anti-drift auditor write block.
  - DEF-BB-018: Expand flight director role resolution keys in anti-drift coordinator write guard.
  - DEF-BB-023: Fallback to workspace dirtyroom cache for external large binaries in REA MCP hook.
- fix(gui): enhance trajectory HUD with dynamic ConnectRPC discovery, subagent tab routing, and timeline zoom controls
- fix(gui): calibrate HUD context metrics to authoritative model usage and fix session title extraction
- fix(gui): calibrate active context tokens to authoritative usage and dynamically populate session dropdown
  - Fix activeTokensSum blowing up to rawSegmentsSum when character heuristic estimates exceed authoritative model usage; now uses selectedEpochTotal as authoritative context size and scales step slices bidirectionally.
  - Dynamically prepend cur.conversation_id to effectiveConvoList when missing from initial static conversation list, preventing `<select id="agyis-convo-select">` from falsely displaying the first conversation.
- fix(gui): eliminate HUD double token reporting and resolve false-positive subagent liveness
  - Remove redundant ${activeTokensSum} / ${totalActiveCapacity} tokens line from HUD context legend, making the top Active Context: ... / 256,000 max the single source of truth.
  - Filter type annotations and generic IDs (_EXCLUDED_CIDS) and prevent run_command outputs from registering phantom spawned subagents in extract_spawned_subagents.
  - Disentangle brain directory matching from role-name matching in probe_subagent_liveness, and apply a 4-hour max age cutoff when not show_all so ancient sessions do not fail invariant checks.
- fix(gui): align ConnectRPC metadata streams, guard checkpoint detection & escape subagent pills
- fix(hooks): route epoch steps through SSOT, detect parent senders & scope compaction advisories
- fix(trajectory): harden checkpoint classification, epoch step SSOT, bounded scan & status provenance
- fix(gui): decouple HUD assets, track SPA routes dynamically, and score per-epoch breakdowns
- fix(hooks): route lifecycle hooks through trajectory SSOT and replace step hard-caps with soft advisories

### Documentation & Usability
- docs(ledger): record Phase 36 cleanroom trajectory HUD & SSOT stock parity integration
- docs(rc10): synchronize ADR index, RE compaction specs, lifecycle hook spec, and roadmap
- docs(rc10): freeze 48 archive docs at 0069329 and leave index trail in docs/archive/README.md
- docs(rc10): consolidate ADRs, specs, runbooks & taxonomy, remediate runtime gaps, scrub PII, and enforce skill ToCs
- docs(rc10): modernize universal_agents template and align specs, ADRs, personas, skills & runbooks
- docs(rc10): archive historical artifacts, consolidate guides, and align specs & ADRs

### Maintenance & Release
- refactor(runtime): enforce PSL-INV-011 module size bounds, modernize SM003/UTF-8 mutator, and parallelize fast-path doctor

---

## [1.0.0-rc10] - 2026-11-10

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
- docs(changelog): update Unreleased entries with gui hydration fix
- docs(changelog): update Unreleased entries with liveness fix
- docs(changelog): update Unreleased entries for RC10 preparation

### Maintenance & Release
- test(ci): align ladder heartbeat benchmark assertion with documented 0.20s SLA for virtualized runners
- chore(release): bump version to 1.0.0-rc10 and stamp CHANGELOG
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

[Unreleased]: https://github.com/kuasha420/agyis-harness/compare/v1.1.1...HEAD
[1.1.1]: https://github.com/kuasha420/agyis-harness/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/kuasha420/agyis-harness/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/kuasha420/agyis-harness/compare/v1.0.0-rc14...v1.0.0
[1.0.0-rc14]: https://github.com/kuasha420/agyis-harness/compare/v1.0.0-rc13...v1.0.0-rc14
[1.0.0-rc13]: https://github.com/kuasha420/agyis-harness/compare/v1.0.0-rc12...v1.0.0-rc13
[1.0.0-rc12]: https://github.com/kuasha420/agyis-harness/compare/v1.0.0-rc11...v1.0.0-rc12
[1.0.0-rc11]: https://github.com/kuasha420/agyis-harness/compare/v1.0.0-rc10...v1.0.0-rc11
[1.0.0-rc10]: https://github.com/kuasha420/agyis-harness/compare/v1.0.0-rc9...v1.0.0-rc10
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
