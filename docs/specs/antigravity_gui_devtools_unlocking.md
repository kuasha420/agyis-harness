<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Google Antigravity Desktop GUI Cleanroom DevTools & Trajectory Debug Specification

- **Document Identifier:** `REA-SPEC-ANTIGRAVITY-GUI-DEVTOOLS-2026-10-17`  
- **Governing Standard:** ADR-028 / Cleanroom Reconstruction (`PSL-INV-007`)  
- **Target Application:** Google Antigravity Desktop (`/opt/Antigravity/antigravity`, v2.19.1, Linux/Wayland)  
- **Analysis Authorities:** Cleanroom ASAR dissection, V8 bundle inspection, Chromium DevTools Protocol (CDP) introspection  

---

## 1. Architecture & Gating Root Causes

Antigravity Desktop runs an Electron host shell (`/opt/Antigravity/resources/app.asar`) rendering a React webview served over loopback HTTPS by `/opt/Antigravity/resources/bin/language_server`.

```text
[1. Electron Host Shell] (/opt/Antigravity/resources/app.asar)
 ├── dist/main.js         Bootstraps --remote-debugging-port=0
 ├── dist/utils.js        BrowserWindow webPreferences.devTools = !app.isPackaged
 ├── dist/menu.js         hideDevTools() sets visible=false on role: 'toggledevtools'
 └── dist/preload.js      Exposes window.electronNative.toggleDevTools()

[2. Chromium CDP Layer]
 └── ~/.config/Antigravity/DevToolsActivePort (Line 1: ephemeral port; Line 2: browser WS path)

[3. React Frontend Client] (https://127.0.0.1:<port>/main.js)
 ├── Feature Flag Provider (oka / mka) <- localStorage["jetski.developer.customFlagOverrides"]
 ├── Command Gate (FPb): vz(n && p ? rla : void 0, ...)
 │    ├── n = !!cascadeId && focusedPane && !isArchived && !isDeleted
 │    └── p = zj().get("trajectoryDebugTools") ?? false
 └── Display Trigger: location.search ?trajectoryDebugOpen=true renders modal EB unconditionally
```

### Empirical Gating Mechanisms
1. **DevTools C++ & Accelerator Suppression**:
   - `dist/utils.js:133` passes `devTools: !electron_1.app.isPackaged`, evaluating to `false` in packaged builds and turning `webContents.openDevTools()` / `toggleDevTools()` (including `window.electronNative.toggleDevTools()` via `dist/preload.js:79` and `dist/ipcHandlers.js:278–283`) into silent no-ops.
   - `dist/menu.js:64–77` hides `toggledevtools` menu items and accelerators (`Ctrl+Shift+I` / `Cmd+Option+I`).
   - Meanwhile, `dist/main.js:115–117` unconditionally appends `--remote-debugging-port=0` whenever not explicitly supplied, publishing the live CDP loopback port in `~/.config/Antigravity/DevToolsActivePort`.
2. **Trajectory Debug View Gating (`main.js` line 10870)**:
   - Command palette registration checks `n && p` for `rla` (`conversationView.openTrajectoryDebugView`), `sla` (`copyConversationId`), and `tla` (`copyTrajectoryId`).
   - `trajectoryDebugTools` feature config defaults to `false` for external users (`userCohort: "external"` vs `["google"]`), unlocking on `runtimeGating.customFlag: "enable-trajectory-debug-tools"`.
   - `Yka` reads `window.localStorage.getItem("jetski.developer.customFlagOverrides")` via React hook `ek(...)` and injects enabled keys into `customFlags` via `Vka()`.
   - Modal `EB` renders unconditionally whenever URL query parameter `?trajectoryDebugOpen=true` is set, bypassing guard `p`.

---

## 2. Cleanroom Unlock Protocols (Zero-Binary-Mutation)

### A. Chromium DevTools Protocol (CDP) Attachment
1. Read port from line 1 of `~/.config/Antigravity/DevToolsActivePort` (or launch `/opt/Antigravity/antigravity --remote-debugging-port=9222`).
2. Attach via `chrome://inspect` (`Discover network targets` -> `127.0.0.1:<port>`) or query target WebSocket URLs at `http://127.0.0.1:<port>/json`.

### B. Feature Flag Injection (`localStorage`)
Evaluating the following in any active page WebSocket target persists command-palette unlock across restarts:
```javascript
localStorage.setItem("jetski.developer.customFlagOverrides", JSON.stringify({
  "enable-trajectory-debug-tools": true,
  "enable-developer-mode": true,
  "enable-split-view": true,
  "enable-thought-editing": true
}));
location.reload();
```

### C. Direct Modal Activation (`?trajectoryDebugOpen=true`)
Setting `url.searchParams.set("trajectoryDebugOpen", "true")` via `window.history.pushState` and dispatching `new PopStateEvent("popstate")` opens the live Trajectory Debug modal (`EB`) without reloading the webview.

*(For offline debugging requiring native in-window `F12`, `app.asar` patching requires setting `devTools: true` in `dist/utils.js`, disabling `hideDevTools(menu)` in `dist/menu.js`, and binding `F12` on `before-input-event` in `dist/keybindings.js`, though CDP protocols preserve update resilience.)*

---

## 3. Empirical Evidence & Verification Audit

All findings in this specification were validated empirically on host `<workstation>` against running instances:

| Evidence ID | Component / Target | Subject / Metric | Verified Value / Finding |
|---|---|---|---|
| `EV-20261017-01` | Host Shell (`app.asar`) | Line 116 of `dist/main.js` | `--remote-debugging-port=0` appended on startup |
| `EV-20261017-02` | Port File | `~/.config/Antigravity/DevToolsActivePort` | Active port `46391` verified live via curl |
| `EV-20261017-03` | Host Shell (`app.asar`) | Line 133 of `dist/utils.js` | `devTools: !electron_1.app.isPackaged` blocks C++ DevTools |
| `EV-20261017-04` | Host Shell (`app.asar`) | Lines 64-77 of `dist/menu.js` | `hideDevTools(menu)` strips accelerator binding |
| `EV-20261017-05` | React Frontend (`main.js`) | Line 10870 of web bundle | `vz(n && p ? rla : void 0, ...)` gating verified |
| `EV-20261017-06` | React Frontend (`main.js`) | Feature Configuration | `trajectoryDebugTools` accepts `customFlag: "enable-trajectory-debug-tools"` |
| `EV-20261017-07` | React Frontend (`main.js`) | `Yka` Provider | `localStorage.getItem("jetski.developer.customFlagOverrides")` overrides flags |
| `EV-20261017-08` | Live React Runtime | React Fiber `#root` Context | `trajectoryDebugTools: true` verified live in memory after `localStorage` update |
| `EV-20261017-09` | Live DOM Modal | Role Dialog `EB` | Trajectory Debug View opened live; verified `144,873 / 256,000 tokens` display |

---

## 4. Product Operationalization (`agyis gui`)

These mechanisms are shipped in `agyis-harness` via `agyis gui` (`harness/cli.py` & `harness/gui/`):
- `agyis gui --devtools`: Reads `~/.config/Antigravity/DevToolsActivePort` and emits CDP targets and `chrome://inspect` URIs.
- `agyis gui --install-launcher`: Installs `~/.local/share/applications/antigravity.desktop` with `Exec=/usr/bin/antigravity --remote-debugging-port=0 %U` so desktop launches emit `DevToolsActivePort`.
- `agyis gui --trajectory-debug` / `--toggle` / `--no-popup`: Performs best-effort `jetski.developer.customFlagOverrides` injection and mounts the In-Situ Trajectory Debug HUD (`#agyis-trajectory-hud`) with persistent `F12` / `Ctrl+Shift+T` hotkeys over live CDP WebSocket without modifying binary files.
- `agyis gui --hud` / `--hud-remove` / `--server` / `--service`: Deploys and manages the live SPA-route-synchronized Trajectory Token HUD overlay and background trajectory API (`--server-port 40624`).

---

## 5. v2.34.0 Upgrade Delta & Empirical Evidence (`2026-11-21`)

Upgrading from Antigravity Desktop `v2.32.1-1` to `v2.34.0-1` (Electron `44.9.1`) introduced three verified behavioral shifts relative to the `v2.19.1`–`v2.32.1` baseline:

1. **Opt-In CDP & Active `DevToolsActivePort` Deletion (`dist/main.js`, `dist/paths.js`, `dist/languageServer.js`):**
   - `v2.32.1` `dist/main.js:133–135` unconditionally called `app.commandLine.appendSwitch('remote-debugging-port', '0')`.
   - `v2.34.0` `dist/main.js` removed the unconditional switch. When `--remote-debugging-port` is absent on CLI, `dist/main.js:372–375` calls `removeStaleActivePortFile(activePortFile)`, deleting `~/.config/Antigravity/DevToolsActivePort`, and `dist/languageServer.js:282–289` withholds `AGY_BROWSER_ACTIVE_PORT_FILE`.
   - `/usr/bin/antigravity` is a direct symlink to the `/opt/Antigravity/antigravity` ELF binary (not a `*-flags.conf` shell wrapper), `/usr/share/applications/antigravity.desktop` runs `Exec=/usr/bin/antigravity %U`, and `dist/main.js:83–87` enforces `app.requestSingleInstanceLock()`, so normal desktop launches emit no CDP port and block secondary `--remote-debugging-port` launches until restarted.
2. **Ephemeral `#t=<bootstrapToken>` Auth Bootstrap (`dist/authBootstrap.js`, `language_server`, `main.js`):**
   - `language_server` now runs with `AGY_REQUIRE_AUTHENTICATED_UI_BOOTSTRAP=1` (`dist/languageServer.js:278`) and serves `window.__APP_CONFIG__.csrfToken = ""` in `index.html`; unauthenticated ConnectRPC calls return HTTP `401` (`missing CSRF token`).
   - `dist/authBootstrap.js` mints a single-use `#t=` token via `POST /auth/mint`, which `main.js` exchanges via `POST /auth` for `sessionToken` and stores in both `window.__APP_CONFIG__.csrfToken` and `localStorage["agy_session_csrf_token"]`.
3. **Native Trajectory Debug View Trigger Change (`main.js` web bundle):**
   - The `?trajectoryDebugOpen=true` query parameter is absent (`0` matches in `v2.34.0` `main.js`). `conversationView.openTrajectoryDebugView` now gates on both `trajectoryDebugTools` and `customSidePanels?.has("trajectoryDebug")`, and `"trajectoryDebug"` is unregistered in `customSidePanels` in packaged external builds (while `canApplyDeveloperOverrides` blocks self-bootstrapping `jetski.developer.customFlagOverrides`). Consequently, the cleanroom In-Situ HUD (`#agyis-trajectory-hud`) is the primary live trajectory inspector in `v2.34.0`.

| Evidence ID | Component / Target | Subject / Digest / Location | Verified Value / Finding |
|---|---|---|---|
| `EV-20261121-01` | Host Shell (`v2.34.0` `app.asar`) | `sha256:8934adef...` (`dist/main.js:372–376`) | Unconditional `--remote-debugging-port=0` removed; `removeStaleActivePortFile` deletes `DevToolsActivePort` when flag absent |
| `EV-20261121-02` | Language Server Spawn (`v2.34.0` `app.asar`) | `dist/languageServer.js:278,282–289` | `AGY_REQUIRE_AUTHENTICATED_UI_BOOTSTRAP=1` set; `AGY_BROWSER_ACTIVE_PORT_FILE` passed only if `--remote-debugging-port` is present |
| `EV-20261121-03` | Live Binary & Launcher (`2.34.0-1`) | `/opt/Antigravity/antigravity` (`sha256:3ba9114b...`), `PID 19680` | ELF fuses have `EnableNodeCliInspectArguments=enabled`; live cmdline `/opt/Antigravity/antigravity` lacks `--remote-debugging-port` |
| `EV-20261121-04` | Language Server HTTP/RPC (`v2.34.0`) | `/opt/Antigravity/resources/bin/language_server` (`sha256:0a044fa3...`) | `GET /` serves `csrfToken: ""`; unauthenticated `Heartbeat`/`GetCascadeTrajectory` return HTTP `401`; `main.js` exchanges `#t=` via `POST /auth` into `window.__APP_CONFIG__.csrfToken` and `localStorage["agy_session_csrf_token"]` |
| `EV-20261121-05` | React Frontend (`v2.34.0` `main.js`) | `https://127.0.0.1:40729/main.js` | `0` matches for `trajectoryDebugOpen`; `conversationView.openTrajectoryDebugView` requires `trajectoryDebugTools` + `customSidePanels.has("trajectoryDebug")` |
