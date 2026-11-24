# Project: Agyis Harness v1.0.0 Architecture & Verification Specification

## Governance (Codex v2)
- **Core Invariants (`PSL-INV-001`–`PSL-INV-008`)**: Empirical Verification & Clean-Room Testing (`PSL-INV-001`), Epistemic Honesty & Observed Evidence (`PSL-INV-002`), Tool Determinism, Failure Transparency & Minimal Diffs (`PSL-INV-003`), Context Signal Hygiene & Runway Discipline (`PSL-INV-004`), Risk-Scaled Planning & Human Steering (`PSL-INV-005`), Independent Verification & Subagent Governance (`PSL-INV-006`), Live Reality Over Static Fakes (`PSL-INV-007`), and Architectural Fitness & Sovereign Boundaries (`PSL-INV-008`, `ADR-014`).
- **On-Demand Domain Pack (`PSL-RE-001`)**: Cleanroom Reverse Engineering & Pre-Analyzed Ghidra Cache loaded via `re-ops`.

## Architecture
- **Harness Core (`harness/`)**: Python 3.12+ CLI, delivery pipeline, harmonization engine, onboard controller, test runner orchestrator, AST smell linter (`harness.doctor.test_smells`), micro-mutator (`harness.mutation.micro_probe`), cleanroom verifier, and DevTools/HUD runtime.
- **In-Situ HUD (`harness/gui/`)**: Modular frontend runtime (`harness/gui/assets/`) injected via Chromium DevTools Protocol (CDP) WebSocket, interfacing with Antigravity Electron shell (`v2.34.0+`) and `language_server` ConnectRPC endpoints.
- **External Target Repositories**: Multi-stack repositories and hermetic temporary fixtures spanning Python, Node/TS, Rust, Go, and monorepos evaluated safely without mutating host state.

## Feature Inventory (Core Surface & E2E Tiers 1–4)
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Harmonization Detection & Migration | Detect legacy `.agent/rules/`, migrate to `.agents/rules/`, rewrite references | M1 | Q1 |
| 2 | Harmonization Safety Archiving | Create compressed tarball and JSON manifest in `.agents/archive/` on `--apply --backup` | M1 | Q1 |
| 3 | Harmonization Tagged Fences & Link Sanitizer | Replace `AGENTS.md` block, rewrite legacy URLs, preserve custom sections | M1 | Q1 |
| 4 | Onboarding Dirty Tree Guard | Halt with code 1 if git working tree has uncommitted changes and `--allow-dirty` omitted | M2 | Q1 |
| 5 | Onboarding Safety Patch Generation | Generate `.agents/artifacts/pre_onboard_safety.patch` diff when `--allow-dirty` enabled | M2 | Q1 |
| 6 | Onboarding Isolated Branch Creation | Check out dedicated branch (e.g. `chore/agyis-harness-onboarding`) and purge build caches | M2 | Q1 |
| 7 | Monorepo Subproject Targeting | Scope harmonization and skill provisioning to subproject path (e.g. `packages/app`) | M2 | Q1 |
| 8 | Multi-Language DRA Test Harmonization | Audit test frameworks and generate `.agyis/test_manifest.json` for Rust & Node/TS | M3 | Q1 |
| 9 | Multi-Language DRA Idempotency | Preserve existing configurations with 0 proposed mutations on pre-harmonized projects | M3 | Q1 |
| 10 | Dynamic SPA Route Switching | Intercept history pushState to track `/c/:id` route transitions in HUD | M4 | Q4 |
| 11 | Active Subagent Window Detection | Prioritize `tab=subagent_convo__<uuid>`, render `(subagent)` badge, and 1-click `← Parent` pill | M4 | Q4 |
| 12 | Live ConnectRPC 60 FPS Streaming | Subscribe to `StreamAgentStateUpdates` and batch DOM updates via rAF coordinator | M4 | Q4 |
| 13 | Live DevTools CDP Controller | Discover active DevTools port, verify CSRF auth, and inject HUD scripts safely | M4 | Q4 |
| 14 | E2E Regression & Tier Verification | Verify all 14 features across Tiers 1-4 against hermetic test suites and live workflows | M5 | All |

## Programmatic Safety Net Feature Anchors (F1–F18)
- **F1–F6 (AST Smell Linter, `harness.doctor.test_smells`)**: Zero-state mock tautology detection (`SM001`), assertion-free test detection (`SM002`), empty/no-op test blocks (`SM003`), echo/mirrored mock assertions (`SM004`), high mock density (`SM005`), and strict `# agyis: no-smell` pragma governance (`F6`).
- **F7–F14 (Diff-Aware Micro-Mutator, `harness.mutation.micro_probe`)**: Condition inversion (`F7`), logical operator swap (`F8`), boundary condition shift (`F9`), return value flip (`F10`), exception swallow check (`F11`), `# agyis: no-mutant` and arid-line exclusions (`F12`), diff-scoped target extraction with backup restoration (`F13`), and baseline sanity + timeout fail-safe (`F14`).
- **F15–F17 (Completion Fence, `harness.hooks.completion_fence_hook`)**: Code-edit dirty tracking (`F15`), tier-aware test verification recording (`F16`), and stop-gate enforcement separating `code_dirty` from `spec_dirty` (`F17`).
- **F18 (Objective Verification & Sub-Second Benchmark)**: Hermetic execution (`<1.0s` per module, `ADR-015`) via `agyis doctor --anti-synthetic`, `agyis test --mutation`, and `agyis audit aff`.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Q1 Harmonization Verification & Archival Decoupling | Verify Python & Rust target migrations and decouple backup archives in `harmonize.py` | none | DONE |
| 2 | Q1 Dirty-Tree Onboarding & Monorepo Subproject | Verify dirty-tree gate, canonical `pre_onboard_safety.patch` output, and monorepo `--subproject` isolation | none | DONE |
| 3 | Q1 Multi-Language DRA Test Harmonization | Verify Rust & Node/TS `.agyis/test_manifest.json` generation, diff scripts, and idempotency | none | DONE |
| 4 | Q4 In-Situ HUD Dogfooding & Subagent Shadowing Fix | Remediate subagent convo shadowing in `hotkey.js`/`hud.js`, wire 60 FPS streaming, verify live routes | none | DONE |
| 5 | Final Milestone: v1.0.0 GA Launch Readiness | Pass 100% of E2E tests (Tiers 1-4), anti-synthetic linter, AFF gate, and isolated wheel verification | M1, M2, M3, M4 | DONE |

## Interface Contracts
### `harness.harmonize` ↔ `harness.cli`
- Subcommand `agyis harmonize <path>`:
  - `--dry-run`: Preview changes, return JSON summary with `success=True`.
  - `--apply --backup`: Create `.agents/archive/legacy-agent-backup-<ts>.tar.gz` and manifest `.json`, migrate rules, update `AGENTS.md`.
### `harness.onboard` ↔ `harness.cli`
- Subcommand `agyis onboard <path>`:
  - If dirty and not `--allow-dirty`: exit 1 with `is_dirty: true`.
  - If `--allow-dirty`: write safety patch to `.agents/artifacts/pre_onboard_safety.patch` (creating a compatibility link/copy at `.agents/artifacts/wip-safety-pre-onboard.patch`).
  - `--subproject <relpath>`: isolate workspace root while keeping git operations at repo root.
### §M2 Interface Contracts (Micro-Mutator, Smell Linter & Completion Fence)
- `harness.mutation.micro_probe.run_micro_mutation(config: MutationConfig) -> MutationResult`: executes baseline check, mutates diff candidates with guaranteed backup rollback, and reports killed vs surviving mutants (`agyis test --mutation`).
- `harness.doctor.test_smells.audit_workspace_test_smells(test_path, repo_root) -> SmellReport`: runs AST smell audit (`agyis doctor --anti-synthetic`).
- `harness.hooks.completion_fence_hook.evaluate_stop(...)`: blocks premature completion when `code_dirty` or `spec_dirty` lacks corresponding post-edit verification.
### `harness.gui` ↔ Antigravity Webview
- URL extraction: Priority 1 to `[?&]tab=subagent_convo__([a-zA-Z0-9_-]+)`, Priority 2 to `/c/([a-zA-Z0-9_-]+)`.
- RPC streaming: `InSituConnectClient.streamConversation(convoId, onFrame)` via `StreamAgentStateUpdates` with CSRF token from `window.__APP_CONFIG__.csrfToken`.

## Code Layout
- `harness/commands/`: CLI subcommands (`harmonize.py`, `onboard.py`, `gui.py`, `test.py`, `doctor.py`, `audit.py`)
- `harness/delivery/`: Core migration, onboarding, and archival logic (`harmonize.py`, `cache.py`, `installer.py`)
- `harness/harmonize/`: Test runner harmonization (`test_runner.py`)
- `harness/doctor/`: Anti-synthetic AST smell linter (`test_smells.py`, `python_smell_visitor.py`, `smell_models.py`)
- `harness/mutation/`: Diff-aware micro-mutator (`micro_probe.py`, `operators.py`, `probe_safety.py`)
- `harness/gui/`: DevTools CDP client (`cdp.py`), trajectory HUD (`trajectory_hud.py`), playback server (`server.py`)
- `harness/gui/assets/`: Frontend modular scripts (`hud.js`, `hotkey.js`, `hud_rpc.js`, `hud_header.js`, `hud_styles.css`)
- `tests/`: Project test suite (`test_harmonize.py`, `test_onboard.py`, `test_gui.py`, `test_e2e_safety_net.py`, `test_micro_probe.py`, etc.)
