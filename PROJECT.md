# Project: Agyis Harness v1.0.0 Full-Surface Bug Bash (Quadrants 1 & 4)

## Architecture
- **Harness Core (`harness/`)**: Python 3.12+ CLI, delivery pipeline, harmonization engine, onboard controller, test runner orchestrator, and DevTools/HUD runtime.
- **In-Situ HUD (`harness/gui/`, `assets/`)**: Modular frontend runtime injected via Chromium DevTools Protocol (CDP) WebSocket, interfacing with Antigravity Electron shell and Go `language_server` ConnectRPC endpoints.
- **External Target Repositories (`/home/kuasha/Dev/`)**: Real codebases spanning diverse stacks (Rust, Node/TS, React Native, Svelte, Tauri, monorepos) subjected to safe, non-destructive evaluation.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Harmonization Detection & Migration | Detect legacy `.agent/rules/`, migrate to `.agents/rules/`, rewrite references | M1 | survey (Target 1A/1B) |
| 2 | Harmonization Safety Archiving | Create compressed tarball and JSON manifest in `.agents/archive/` on `--apply --backup` | M1 | survey (Defect 2) |
| 3 | Harmonization Tagged Fences & Link Sanitizer | Replace `AGENTS.md` block, rewrite legacy URLs, preserve custom sections | M1 | survey (Target 1B) |
| 4 | Onboarding Dirty Tree Guard | Halt with code 1 if git working tree has uncommitted changes and `--allow-dirty` omitted | M2 | survey (Target 2) |
| 5 | Onboarding Safety Patch Generation | Generate `.agents/artifacts/pre_onboard_safety.patch` diff when `--allow-dirty` enabled | M2 | survey (Defect 1) |
| 6 | Onboarding Isolated Branch Creation | Check out dedicated branch (e.g. `chore/onboard-eval`) and purge build caches | M2 | survey (Target 2) |
| 7 | Monorepo Subproject Targeting | Scope harmonization and skill provisioning to subproject path (e.g. `packages/react`) | M2 | survey (Target 3) |
| 8 | Multi-Language DRA Test Harmonization | Audit test frameworks and generate `.agyis/test_manifest.json` for Rust & Node/TS | M3 | survey (Target 4A/4B) |
| 9 | Multi-Language DRA Idempotency | Preserve existing configurations with 0 proposed mutations on pre-harmonized projects | M3 | survey (Target 4B) |
| 10 | Dynamic SPA Route Switching | Intercept history pushState to track `/c/:id` route transitions in HUD | M4 | survey (Q4 HUD) |
| 11 | Active Subagent Window Detection | Prioritize `tab=subagent_convo__<uuid>`, render `(subagent)` badge, and 1-click `← Parent` pill | M4 | survey (Defect 5) |
| 12 | Live ConnectRPC 60 FPS Streaming | Subscribe to `StreamAgentStateUpdates` and batch DOM updates via rAF coordinator | M4 | survey (Defect 6) |
| 13 | Live DevTools CDP Controller | Discover active DevTools port, verify CSRF auth, and inject HUD scripts safely | M4 | survey (Q4 HUD) |
| 14 | E2E Regression & Tier Verification | Verify all 14 features across Tiers 1-4 against test suite and live dogfooding | M5 | survey (All) |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Q1 Harmonization Verification & Archival Decoupling | Verify ModMail-Bot and purrfect-download-manager, decouple backup archive in `harmonize.py` | none | DONE |
| 2 | Q1 Dirty-Tree Onboarding & Monorepo Subproject | Verify dream-emirates-app dirty gate, patch naming alias, chakra-ui subproject onboarding | none | DONE |
| 3 | Q1 Multi-Language DRA Test Harmonization | Verify immortal (Rust) and jimha (Node/TS) test manifest generation, diff scripts & idempotency | none | DONE |
| 4 | Q4 In-Situ HUD Dogfooding & Subagent Shadowing Fix | Remediate subagent convo shadowing in hotkey/hud/commands, wire 60 FPS streaming, dogfood live | none | DONE |
| 5 | Final Milestone: E2E Test Pass & Coverage Hardening | Pass 100% of E2E tests (Tiers 1-4) published by E2E Testing Track, then Tier 5 adversarial sweep | M1, M2, M3, M4 | DONE |

## Interface Contracts
### `harness.harmonize` ↔ `harness.cli`
- Subcommand `agyis harmonize <path>`:
  - `--dry-run`: Preview changes, return JSON summary with `success=True`.
  - `--apply --backup`: Create `.agents/archive/legacy-agent-backup-<ts>.tar.gz` and manifest `.json`, migrate rules, update `AGENTS.md`.
### `harness.onboard` ↔ `harness.cli`
- Subcommand `agyis onboard <path>`:
  - If dirty and not `--allow-dirty`: exit 1 with `is_dirty: true`.
  - If `--allow-dirty`: write safety patch to `.agents/artifacts/pre_onboard_safety.patch` (with backward-compatible symlink to `wip-safety-pre-onboard.patch`).
  - `--subproject <relpath>`: isolate workspace root while keeping git operations at repo root.
### `harness.gui` ↔ Antigravity Webview
- URL extraction: Priority 1 to `[?&]tab=subagent_convo__([a-zA-Z0-9_-]+)`, Priority 2 to `/c/([a-zA-Z0-9_-]+)`.
- RPC streaming: `InSituConnectClient.streamConversation(convoId, onFrame)` via `StreamAgentStateUpdates` with CSRF token from `window.__APP_CONFIG__.csrfToken`.

## Code Layout
- `harness/commands/`: CLI subcommands (`harmonize.py`, `onboard.py`, `gui.py`)
- `harness/delivery/`: Core migration and archival logic (`harmonize.py`, `cache.py`)
- `harness/harmonize/`: Test runner harmonization (`test_runner.py`)
- `harness/gui/`: DevTools CDP client (`cdp.py`), trajectory HUD (`trajectory_hud.py`), playback server (`server.py`)
- `harness/gui/assets/`: Frontend modular scripts (`hud.js`, `hotkey.js`, `hud_rpc.js`, `hud_header.js`, `hud_styles.css`)
- `tests/`: Project test suite (`test_harmonize.py`, `test_onboard.py`, `test_gui.py`, etc.)
