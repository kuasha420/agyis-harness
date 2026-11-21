<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Antigravity Platform Compatibility & Drift Inventory (`v2.34.0`)

- **Document Identifier:** `REA-INV-ANTIGRAVITY-V2_34-2026-11-21`
- **Governing Standards:** ADR-014, ADR-028, Cleanroom Invariants (`PSL-INV-007`), Anti-Vibe (`PSL-INV-010`)
- **Purpose:** Canonical living inventory tracking breaking deltas and compatibility drift between `agyis-harness` (`v1.0.0-rc11`) and the upgraded Google Antigravity platform stack installed on `2026-11-21`.

---

## 1. Audited Platform Surface Baseline (`2026-11-21`)

| Surface | Package / Binary | Installed Version | SHA-256 Digest |
| :--- | :--- | :--- | :--- |
| **Antigravity Desktop Shell** | `antigravity` (`/opt/Antigravity/antigravity`) | `2.34.0-1` (Electron `44.9.1`) | `3ba9114b7fbaafaf548f72c5d1bc86b7dc81098a85361784359c2c1199625bfc` |
| **Antigravity Desktop ASAR** | `/opt/Antigravity/resources/app.asar` | `2.34.0` | `8934adef0622c9271c92eea950a71848764a66f7b10023ccbd82e54b959adb0e` |
| **Jetski Language Server** | `/opt/Antigravity/resources/bin/language_server` | `2.34.0` bundle | `0a044fa38f30dc14363a4450fb0f39f00000834e99b52f12b92ba98b24ad10b9` |
| **Antigravity CLI** | `antigravity-cli` (`/usr/bin/agy`) | `1.5.14` | `37873b8062391b6202a3d3199ec012abc9e53aab720d26cd65699441497d8c94` |
| **Antigravity IDE** | `antigravity-ide` (`/opt/antigravity-ide/bin/antigravity-ide`) | `2.8.0-1` | `5916fa84c6f436635ce1314573bfe860605258867590664c22efd476d353f9207` |

---

## 2. Recorded Discrepancies & Drift Entries

| Drift ID | Subsystem / Feature | Severity | Status | Impacted `agyis` Files | Verified Platform Evidence & Root Cause |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **`AGY-DRIFT-001`** | **GUI CDP Port Discovery (`agyis gui`, `systemd`)** | `P0` (Blocker) | Confirmed | [`harness/commands/gui.py`](../../harness/commands/gui.py), [`harness/gui/cdp.py`](../../harness/gui/cdp.py), [`harness/gui/systemd.py`](../../harness/gui/systemd.py), [`docs/specs/antigravity_gui_devtools_unlocking.md`](antigravity_gui_devtools_unlocking.md) | `v2.34.0` removed unconditional `--remote-debugging-port=0` from `dist/main.js` (present in `v2.32.1:133–135`). `dist/main.js:372–375` now deletes `~/.config/Antigravity/DevToolsActivePort` via `removeStaleActivePortFile` whenever `--remote-debugging-port` is omitted. `/usr/bin/antigravity` is an ELF symlink (no `*-flags.conf` wrapper), `/usr/share/applications/antigravity.desktop` passes no debug flag, and `app.requestSingleInstanceLock()` (`dist/main.js:83–87`) prevents attaching a second instance while running. |
| **`AGY-DRIFT-002`** | **HUD ConnectRPC Auth / CSRF Fallback (`hud_rpc.js`)** | `P1` (High) | Confirmed | [`harness/gui/assets/hud_rpc.js`](../../harness/gui/assets/hud_rpc.js#L626), [`harness/commands/gui.py`](../../harness/commands/gui.py#L129) | `v2.34.0` sets `AGY_REQUIRE_AUTHENTICATED_UI_BOOTSTRAP=1` and serves `window.__APP_CONFIG__.csrfToken = ""` in `GET /` (`dist/authBootstrap.js`). Unauthenticated `Heartbeat` / `GetCascadeTrajectory` calls return HTTP `401`. The Hub exchanges `#t=<bootstrapToken>` via `POST /auth` into `window.__APP_CONFIG__.csrfToken` and `localStorage["agy_session_csrf_token"]`. `hud_rpc.js:626` reads only `window.__APP_CONFIG__.csrfToken` without falling back to `localStorage.getItem("agy_session_csrf_token")`, risking `401` fallbacks to port `40624` on reloads or secondary contexts. |
| **`AGY-DRIFT-003`** | **Native Trajectory Debug View Trigger (`?trajectoryDebugOpen`)** | `P2` (Medium) | Confirmed | [`harness/commands/gui.py`](../../harness/commands/gui.py#L259-L261), [`harness/commands/gui.py`](../../harness/commands/gui.py#L614), [`docs/specs/antigravity_gui_devtools_unlocking.md`](antigravity_gui_devtools_unlocking.md) | `v2.34.0` `main.js` removed `?trajectoryDebugOpen=true` (`0` matches). Native `conversationView.openTrajectoryDebugView` now gates on both `trajectoryDebugTools` and `customSidePanels?.has("trajectoryDebug")` and opens `{type: "customView", customView: {customPaneKey: "trajectoryDebug"}}`. Cleanroom `#agyis-trajectory-hud` remains independent, but returned URL params and CLI messaging reference obsolete native behavior. |

---

## 3. Holistic Swarm Sweep Coverage Matrix

Tracked for population following independent verification by the `/swarm` audit cohort:

| Workstream Owner | Subsystem Scope | Audit Status |
| :--- | :--- | :--- |
| `audit-hooks` | `hooks.json`, `harness/hooks/*`, `harness/rules/*` vs. `v2.34.0` / `agy 1.5.14` native tool names & hook schemas | Queued (Swarm) |
| `audit-trajectory` | `harness/trajectory/*`, `harness/telemetry/*`, `pipeline/*`, `sync`, `audit`, `status`, `checkpoint` vs. live SQLite/protobuf/transcripts | Queued (Swarm) |
| `audit-agents` | `harness/subagents/*`, `harness/agents/*`, `harness/skills/*`, `cockpit`, `router`, `subagents` vs. `v2.34.0` native tools, `/swarm`, builtin skills & slash commands | Queued (Swarm) |
| `audit-surfaces` | `harness/delivery/*`, `harness/harmonize/*`, `harness/doctor/*`, `harness/remote/*`, `harness/runtime/*`, `onboard`, `init`, `install`, `clean`, `ext` vs. `v2.34.0` / `agy 1.5.14` / `antigravity-ide 2.8.0` | Queued (Swarm) |
| `audit-gui-re` | `harness/gui/*`, `harness/re/*`, `harness/cleanroom/*`, `gui`, `re`, `verify` vs. `v2.34.0` `BaseWindow`/`WebContentsView`, HUD assets & `rea` tooling | Queued (Swarm) |
| `verifier` | Independent empirical cross-check, test suite / AFF / `verify --spec` baseline, and consolidated severity-ranked triage | Queued (Swarm) |
