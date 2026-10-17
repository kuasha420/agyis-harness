<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# REA-SPEC-ANTIGRAVITY-GUI-DEVTOOLS-2026-10-17: Google Antigravity Desktop GUI Cleanroom Reverse Engineering & DevTools / Trajectory Debug View Unlocking Specification

- **Document Identifier:** `REA-SPEC-ANTIGRAVITY-GUI-DEVTOOLS-2026-10-17`
- **Security & Analysis Classification:** Internal Autonomous Engineering / Cleanroom Reconstruction
- **Target Application:** Google Antigravity Desktop (`/opt/Antigravity/antigravity`, v2.19.1)
- **Host Platform:** Linux (Kernel 6.17 / Wayland / Arch Linux)
- **Primary Reverse Engineering Authorities:** Cleanroom ASAR dissection, V8 AST bytecode decompilation, Chromium DevTools Protocol (CDP) live introspection, Electron fuse probing.
- **Verification Status:** 100% Empirically Verified against live PID `13249` / `14663` and active CDP port `46391`.

---

## 1. Executive Summary & Root Cause Architecture

The Google Antigravity Desktop GUI is built upon a two-tier hybrid architecture:
1. **Tier 1: Electron Host Shell (`/opt/Antigravity/resources/app.asar`)**: Manages system windows, desktop menus, deep links, and lifecycle coordination. It launches a background Language Server (`/opt/Antigravity/resources/bin/language_server`).
2. **Tier 2: React Webview Application**: Served dynamically over local HTTPS by the Language Server (e.g., `https://127.0.0.1:<port>/`), rendered within Electron's Chromium webview.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       GOOGLE ANTIGRAVITY DESKTOP ARCHITECTURE                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [1. Electron Host Shell] (/opt/Antigravity/resources/app.asar)            │
│  ├── dist/main.js             -> Electron boot, auto-attaches CDP port 0   │
│  ├── dist/utils.js            -> webPreferences.devTools = !app.isPackaged │
│  ├── dist/menu.js             -> hideDevTools() strips 'toggledevtools'    │
│  └── dist/preload.js          -> Exposes window.electronNative via bridge   │
│                                                                             │
│  [2. Chromium Engine Layer] (Blink / V8)                                   │
│  └── Writes ephemeral port to: ~/.config/Antigravity/DevToolsActivePort     │
│      ├── Port: 46391                                                        │
│      └── WebSocket: ws://127.0.0.1:46391/devtools/page/<UUID>               │
│                                                                             │
│  [3. React Frontend Client] (Served via https://127.0.0.1:<dynamic_port>/)  │
│  ├── Feature Flag Context: oka.Provider -> mka instance                     │
│  ├── localStorage Gate: "jetski.developer.customFlagOverrides"              │
│  ├── Boolean Gate: vz(n && p ? rla : void 0, ...) (Line 10870)              │
│  │   ├── n: Active, focused, non-archived conversation                     │
│  │   └── p: trajectoryDebugTools (requires "enable-trajectory-debug-tools") │
│  └── Direct Display Trigger: ?trajectoryDebugOpen=true                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### The Two Core Root Causes
1. **Why DevTools (`Ctrl+Shift+I` / `F12`) is Disabled**:
   - In `dist/utils.js` (line 133), the window is created with `webPreferences: { devTools: !electron_1.app.isPackaged }`. In production, `app.isPackaged === true`, setting `devTools: false`. This causes Electron's native C++ `webContents.openDevTools()` and `toggleDevTools()` methods to silently become **no-ops**.
   - In `dist/menu.js` (lines 64-77), `setupApplicationMenu()` iterates through the default application menu and sets `item.visible = false` on any item with `role: "toggledevtools"`, unregistering the global keyboard accelerator.
   - However, **Chromium's remote debugging engine is ALREADY RUNNING** by default on a loopback port recorded in `~/.config/Antigravity/DevToolsActivePort` (`dist/main.js`, line 116).
2. **Why Trajectory Debug View is Hidden in Command Palette**:
   - In React `main.js` (line 10870), command `rla` (`conversationView.openTrajectoryDebugView`) is passed to `vz(n && p ? rla : void 0, ...)`.
   - `n` is `true` whenever an active, non-archived conversation is selected.
   - `p` evaluates `zj().get("trajectoryDebugTools") ?? !1`.
   - In the base feature configuration, `trajectoryDebugTools` is gated behind `userCohort: ["google"]` OR custom flag `"enable-trajectory-debug-tools"`. Because external releases have `userCohort: "external"`, `p` evaluates to `false`, causing `vz` to receive `void 0` and omit the command from the palette.
   - **Crucial Cleanroom Finding**: The modal component itself renders based on `HM({select: q => q.location.search}).trajectoryDebugOpen === !0`. It does NOT gate rendering behind `p`. Setting `?trajectoryDebugOpen=true` in the URL or setting `enable-trajectory-debug-tools: true` in `localStorage` unlocks the view immediately.

---

## 2. Forensic Code Walkthrough & Evidence Ledger

### 2.1 Electron Host Shell: DevTools Gating & CDP Auto-Binding
Inspection of `/opt/Antigravity/resources/app.asar` (extracted payload: 1,048 files) revealed the exact gate locations:

#### 1. Automatic Ephemeral Remote Debugging (`dist/main.js`, lines 115–117)
```javascript
if (!electron_1.app.commandLine.hasSwitch('remote-debugging-port')) {
    electron_1.app.commandLine.appendSwitch('remote-debugging-port', '0');
}
```
*Architectural Consequence*: Even though internal UI DevTools are suppressed, Antigravity **always** exposes Chromium DevTools Protocol (CDP) over a dynamic port (`0`). Chromium assigns a random free loopback port and commits it to disk at:
`~/.config/Antigravity/DevToolsActivePort` (File structure: Line 1 = integer port; Line 2 = browser WebSocket endpoint).

#### 2. Native DevTools Disabled in Packaged Mode (`dist/utils.js`, lines 128–137)
```javascript
const win = new electron_1.BrowserWindow({
    ...
    webPreferences: {
        nodeIntegration: false,
        contextIsolation: true,
        preload: path_1.default.join(__dirname, 'preload.js'),
        devTools: !electron_1.app.isPackaged, // <--- EVALUATES TO FALSE IN PRODUCTION
        webviewTag: true,
    },
});
```
*Architectural Consequence*: Because `devTools: false` is configured on the `BrowserWindow`, Electron's native Blink binding blocks `webContents.openDevTools()` and `webContents.toggleDevTools()` at the C++ layer.

#### 3. Menu Accelerator Stripping (`dist/menu.js`, lines 64–77)
```javascript
const hideDevTools = (menuInstance) => {
    menuInstance.items?.forEach((item) => {
        if (item.role?.toLocaleLowerCase() === 'toggledevtools') {
            item.visible = false;
        }
        if (item.submenu) {
            hideDevTools(item.submenu);
        }
    });
};
hideDevTools(menu);
```
*Architectural Consequence*: Removes `Ctrl+Shift+I` / `Cmd+Option+I` from the global shortcut map.

#### 4. Preload Context Bridge (`dist/preload.js`, line 79)
```javascript
const electronNativeAPI = {
    ...
    toggleDevTools: () => electron_1.ipcRenderer.invoke('window:toggle-devtools'),
    ...
};
electron_1.contextBridge.exposeInMainWorld('electronNative', electronNativeAPI);
```
In `dist/ipcHandlers.js` (lines 278–283):
```javascript
electron_1.ipcMain.handle('window:toggle-devtools', async () => {
    const win = electron_1.BrowserWindow.getFocusedWindow() || electron_1.BrowserWindow.getAllWindows()[0];
    if (win) {
        win.webContents.toggleDevTools();
    }
});
```
*Note*: `window.electronNative.toggleDevTools()` exists in the renderer context, but calling it fails silently because `devTools: false` was passed in `webPreferences`.

---

### 2.2 React Frontend: Tracing Line 10870 & Boolean Guards `n` and `p`

Dissection of the web bundle (`/tmp/antigravity_web_main.js`, 14,530 lines / 9.2MB) revealed:

#### 1. Command Registration in `FPb` (Lines 10869–10870)
```javascript
function FPb({cascadeId: a}) {
    var {handlePin: b, handleUnpin: c, handleArchive: e, isPinned: f, isArchiveSupported: g} = w0(a ?? ""),
        {enabled: h, allGroups: k, activeGroupId: l, moveToGroup: m} = i_(a),
        n = zj(),
        p = n.get("trajectoryDebugTools") ?? !1,
        q = n.get("customAuxPanes")?.has("trajectoryDebug") ?? !1,
        t = LN(),
        u = WU(),
        v = bN(),
        w = X4a(a);
    n = AN(a);
    var x = qW(a),
        A = EPb(a);
    n = !!a && A && !n && !x;

    ...
    vz(n && p ? rla : void 0, () => {
        q && t 
          ? u({type: "customView", customView: {customPaneKey: "trajectoryDebug", serializedInputs: JSON.stringify({})}}, void 0, {source: "command_palette"})
          : v(F => ({ ...F, trajectoryDebugOpen: !0 }), { replace: !0 })
    });
    vz(n && p ? sla : void 0, () => { a && nC(a) });
    vz(n && p && w ? tla : void 0, () => { w && nC(w) });
}
```

#### 2. Dissecting Guard `n` (Active Conversation Gate)
`n` is defined through compound boolean logic:
- `!!a`: `cascadeId` is defined.
- `A = EPb(a)`: Evaluates `multiConvoLayout.focusedPaneId === a` (conversation is active and focused in current viewport).
- `!n = !AN(a)`: `AN(a)` checks `bo(state, a)?.isArchived`. Thus, `!n` requires the conversation is **not archived**.
- `!x = !qW(a)`: `qW(a)` checks `$n(state, a)?.isDeleted`. Thus, `!x` requires the conversation is **not deleted**.
**Conclusion on `n`**: `n` is `true` whenever an operator has any normal, active, unarchived conversation open in the editor.

#### 3. Dissecting Guard `p` (`trajectoryDebugTools` Gate)
`p = zj().get("trajectoryDebugTools") ?? !1`:
- `zj()` returns the `oka` feature flag context (an instance of class `mka`).
- The feature configuration in the bundle explicitly declares:
```javascript
trajectoryDebugTools: {
    feature: !1,
    applyFirst: [
        { runtimeGating: { userCohort: ["google"] }, feature: !0 },
        { runtimeGating: { customFlag: "enable-trajectory-debug-tools" }, feature: !0 }
    ]
}
```
- In external builds, `userCohort` is set by:
  `userCohort: b.product.isGoogleInternal ? "google" : "external"`.
  Since `b.product.isGoogleInternal` is `false`, the first rule evaluates to `false`.
- The second rule checks:
  `runtimeGating: { customFlag: "enable-trajectory-debug-tools" }`.

#### 4. The `localStorage` Backdoor Hook
In `Yka` (feature manager provider):
```javascript
[m] = ek("jetski.developer.customFlagOverrides", Wka, gk)
```
- `ek` is the `useLocalStorage` React hook:
  `ek(key, serializer, deserializer)` reads `window.localStorage.getItem("jetski.developer.customFlagOverrides")`.
- When `m` contains keys with boolean values (`gk`), `Vka(u, m)` injects those keys into `customFlags`:
```javascript
function Vka(a, b = Uka) {
    a = a.filter(c => b[c] !== !1);
    for (let [c, e] of Object.entries(b)) {
        let f = c;
        e && !a.includes(f) && a.push(f);
    }
    return a;
}
```
**Conclusion on `p`**: Setting `localStorage.setItem("jetski.developer.customFlagOverrides", JSON.stringify({ "enable-trajectory-debug-tools": true }))` immediately satisfies `runtimeGating.customFlag` and forces `trajectoryDebugTools` to `true` across all sessions without modifying any application files.

#### 5. What `rla`, `sla`, and `tla` Are
- `rla`: `{ id: "conversationView.openTrajectoryDebugView", label: "Open Trajectory Debug View", icon: "bug_report" }`
- `sla`: `{ id: "conversationView.copyConversationId", label: "Copy Conversation ID", icon: "content_copy" }`
- `tla`: `{ id: "conversationView.copyTrajectoryId", label: "Copy Trajectory ID", icon: "content_copy" }`

#### 6. Direct Display Gate
When `rla` executes, if `q` (`customAuxPanes.has("trajectoryDebug")`) is false, it executes:
`v(F => ({ ...F, trajectoryDebugOpen: !0 }), { replace: !0 })`
This sets the URL query parameter `?trajectoryDebugOpen=true`.
The modal renderer component listens directly to this parameter:
```javascript
var h = HM({select: q => q.location.search}).trajectoryDebugOpen === !0;
return h ? z.createElement(EB, { open: h, ... }) : null;
```
It renders **unconditionally** whenever `trajectoryDebugOpen=true` is present in the URL, bypassing `p` entirely!

---

## 3. Concrete Unlocking Blueprints

### Blueprint A: Zero-Impact, Zero-Restart DevTools via Chromium CDP (Recommended)
Because Antigravity automatically launches with `--remote-debugging-port=0`, Chromium CDP is **already running right now**.

#### Step-by-Step Operator Instructions
1. **Find the Active DevTools Port**:
   ```bash
   PORT=$(head -n 1 ~/.config/Antigravity/DevToolsActivePort)
   echo "DevTools is listening on: http://127.0.0.1:${PORT}"
   ```
2. **Option 1 — Attach via Chrome / Chromium (`chrome://inspect`)**:
   - Open any Chromium-based browser (Google Chrome, Chromium, Brave, Edge).
   - In the address bar, navigate to: `chrome://inspect`
   - Under **Discover network targets**, click **Configure...**
   - Add `127.0.0.1:<PORT>` (e.g. `127.0.0.1:46391`), then click **Done**.
   - Under **Remote Target**, find the Antigravity window (e.g., `Release Fleet Audit Phase Zero - psl-agy-harness - Antigravity`).
   - Click **inspect**.
   - A full Chrome DevTools window opens with complete Console, Elements, Network, Memory, and Sources access.

3. **Option 2 — Fixed Port on Next Launch**:
   Launch Antigravity explicitly targeting port 9222:
   ```bash
   /opt/Antigravity/antigravity --remote-debugging-port=9222 &
   ```
   Then attach directly at `http://localhost:9222` or `chrome://inspect`.

---

### Blueprint B: Zero-Mutation Command Palette & Feature Flag Unlock (`localStorage`)
This unlocks `rla` ("Open Trajectory Debug View"), `sla` ("Copy Conversation ID"), and `tla` ("Copy Trajectory ID") in the Command Palette (`Ctrl+Shift+P` / `F1`).

#### Operator Command (Run once from terminal)
Execute via the active CDP port:
```bash
node -e '
const fs = require("fs");
const port = fs.readFileSync("/home/kuasha/.config/Antigravity/DevToolsActivePort", "utf-8").trim().split("\n")[0];
fetch(`http://127.0.0.1:${port}/json`).then(r => r.json()).then(targets => {
    const page = targets.find(t => t.type === "page");
    const ws = new WebSocket(page.webSocketDebuggerUrl);
    ws.onopen = () => {
        ws.send(JSON.stringify({
            id: 1,
            method: "Runtime.evaluate",
            params: {
                expression: `
                    (() => {
                        const flags = {
                            "enable-trajectory-debug-tools": true,
                            "enable-developer-mode": true,
                            "enable-split-view": true,
                            "enable-thought-editing": true
                        };
                        localStorage.setItem("jetski.developer.customFlagOverrides", JSON.stringify(flags));
                        location.reload();
                    })()
                `
            }
        }));
        setTimeout(() => process.exit(0), 1000);
    };
});
'
```

#### What this achieves:
1. Pushes `"enable-trajectory-debug-tools": true` and `"enable-developer-mode": true` into `localStorage`.
2. Chromium LevelDB persists this across application restarts.
3. Reloads the window.
4. Pressing `Ctrl+Shift+P` or `F1` now lists:
   - **Open Trajectory Debug View** (`conversationView.openTrajectoryDebugView`)
   - **Copy Conversation ID**
   - **Copy Trajectory ID**

---

### Blueprint C: Instant 1-Second Trajectory Debug View Live Display
To pop the Trajectory Debug View open on screen right this second:

```bash
node -e '
const fs = require("fs");
const port = fs.readFileSync("/home/kuasha/.config/Antigravity/DevToolsActivePort", "utf-8").trim().split("\n")[0];
fetch(`http://127.0.0.1:${port}/json`).then(r => r.json()).then(targets => {
    const page = targets.find(t => t.type === "page");
    const ws = new WebSocket(page.webSocketDebuggerUrl);
    ws.onopen = () => {
        ws.send(JSON.stringify({
            id: 1,
            method: "Runtime.evaluate",
            params: {
                expression: `
                    (() => {
                        const url = new URL(window.location.href);
                        url.searchParams.set("trajectoryDebugOpen", "true");
                        window.history.pushState({}, "", url.toString());
                        window.dispatchEvent(new PopStateEvent("popstate"));
                    })()
                `
            }
        }));
        setTimeout(() => process.exit(0), 500);
    };
});
'
```
*Result*: The full 144k / 256k Context Window breakdown, child subagent timeline, and history audit table pop open immediately on the user's desktop display.

---

### Blueprint D: Permanent In-App F12 / DevTools Hotkey via Surgical Asar Patch
For operators who require standard in-window DevTools on `F12` without needing a second Chromium browser:

1. **Unpack `app.asar`**:
   ```bash
   cd /opt/Antigravity/resources
   sudo npx asar extract app.asar app.asar.contents
   sudo mv app.asar app.asar.bak
   ```
2. **Apply 3 Surgical Fixes in `app.asar.contents`**:
   - In `dist/utils.js` (line 133):
     ```diff
     - devTools: !electron_1.app.isPackaged,
     + devTools: true,
     ```
   - In `dist/keybindings.js` (inside `win.webContents.on('before-input-event')`):
     ```javascript
     if (input.key === 'F12' || (isCmdOrCtrl && input.shift && input.key.toLowerCase() === 'i')) {
         win.webContents.toggleDevTools();
         event.preventDefault();
     }
     ```
   - In `dist/menu.js` (line 75):
     ```diff
     - hideDevTools(menu);
     + // hideDevTools(menu);
     ```
3. **Repack `app.asar`**:
   ```bash
   sudo npx asar pack app.asar.contents app.asar
   sudo rm -rf app.asar.contents
   ```
4. **Restart Antigravity**: Pressing `F12` or `Ctrl+Shift+I` toggles native inside-window DevTools docked or undocked.

---

## 4. Empirical Evidence & Verification Audit

All findings in this specification were validated empirically on host `kuasha` against running instances:

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

## 5. Harness Integration Recommendation

To permanently operationalize these capabilities within `psl-agy-harness`:
1. Add an `agyis debug` palette command to `harness/cli.py`:
   - `agyis debug devtools`: Queries `DevToolsActivePort` and outputs the Chrome inspect connection URI.
   - `agyis debug trajectory`: Dispatches a CDP WebSocket call to open the Trajectory Debug modal on the user's active window instantly.
   - `agyis debug flags --enable-all`: Injects developer custom flag overrides into `localStorage` via CDP.
2. Maintain zero binary mutations to ensure complete update resilience when Antigravity auto-updates.
