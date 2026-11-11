<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Google Antigravity UI Token Surfacing & Urgency Architecture
## Cleanroom Empirical Reverse Engineering Specification

**Document Identifier:** `REA-SPEC-ANTIGRAVITY-UI-TOKEN-SURFACING-2026-10-17`  
**Governing Standard:** ADR-028 / ADR-033 / Cleanroom Standards (`PSL-INV-007`)  
**Analysis Provider:** REA v6.5.0 (`inspect-go-binary`, `sqlite`, `asar-dissect`, `v8-bundle-tracer`)  
**Target Architectures:** Google Antigravity Desktop GUI v2.19.1 (CL `951519500`) & `/usr/bin/agy` CLI v1.3.1 (CL `985595000`)  

---

## 1. Empirical Discoveries & Immutable Evidence

1. **Hidden Native Context Visualizer (`j5b`)**: Antigravity implements a multi-segment token bar (`j5b` in `main.js`, lines `12006–12020`) inside the Trajectory Debug modal (`T6b -> S6b -> C6b -> j5b`), hidden unless opened via `conversationView.openTrajectoryDebugView` (`rla`) or `?trajectoryDebugOpen=true`.
2. **Connect-RPC State Stream**: The React client consumes live step and token updates over `@connectrpc/connect-web` (`StreamAgentStateUpdates` via `Hca()` -> `Eca()` reducer -> `agentStateProvider.trajectorySlice`).
3. **Terminal CLI Token Pipeline**: `/usr/bin/agy` (Charmbracelet Bubble Tea v2) computes session token totals via `steps.CalculateTokenSums` and renders header/compaction telemetry via `render.FormatTokens` and `render.renderCompactionMarker`.

### Immutable Evidence Index

| Evidence ID | Subject Path | SHA-256 Digest | Provider / Engine | Scope & Findings |
|:---|:---|:---|:---|:---|
| `ev_10ce7489bb41094da55b70...` | `https://localhost:37277/main.js` | `3715c65f9737155e744a56a64be57da33ea7e64da4b10467b938fefcfeb1bbff` | REA `v8-bundle-tracer` | Frontend React client: `j5b` token bar, `Xsb` turn list, `Qrb` active hook, `P6b` header |
| `ev_38fb29910d64a0280b271a...` | `/opt/Antigravity/resources/app.asar` | `9b36d0124ad1830119e7a6fcaeb34bfcfcf1daef50ecfa6067b8a7f9202a63d1` | REA `asar-dissect` | Electron host: `dist/preload.js` bridge, `dist/main.js`, `dist/hostBridgeServer.js` |
| `ev_7b2e182eb1213cdf44aeb6...` | `/usr/bin/agy` | `ce1bdaed3201bb84f35d69d2773caec4f18af52af00e8c25f6cace07e4359615` | REA `inspect-go-binary` (Go 1.28 `cl/985595000`) | Terminal CLI: Bubble Tea v2, `render/compaction_marker.go`, `steps/steps.CalculateTokenSums` |
| `ev_9a6fd366f2d157ce803cde...` | `/opt/Antigravity/resources/bin/language_server` | `2dce14e864bf5cb7fea8bdce56741570ce8a0efad00e9527224f0950d26ce891` | REA `inspect-go-binary` (Go 1.28 `cl/951519500`) | Engine Cortex scheduler, `StreamAgentStateUpdates` Connect-RPC server stream |
| `ev_a74158469a14d3141c3dfb...` | `~/.gemini/antigravity/conversations/<id>.db` | Dynamically generated SQLite | REA `inspect-sqlite-database` (SQLite 3.53.4) | `steps` table containing raw `step_data` JSON with step token counts |

---

## 2. Desktop Webview State Path & DOM Anchors

### 2.1 `trajectorySlice` Data Path & Segment Matrix
Streaming token state populates:
```text
agentStateProvider -> trajectorySlice
 ├── generatorMetadatasInSlice[].metadata.value
 │    ├── messagePrompts[0].numTokens
 │    ├── toolCallOutputTokens
 │    └── modelUsage.outputTokens
 ├── stepsInSlice[]
 └── chatStartMetadata.contextWindowMetadata.maxContextTokens (256000)
```
When `numTokens` is absent mid-stream, `main.js` falls back to `round((thinking.length + prompt.length) / 3.5)`.

The `j5b` visualizer assigns fixed color tokens per context segment:
- System Prompt (`bg-indigo-500`), Tool Definitions (`bg-cyan-500`), Trajectory Checkpoint (`bg-green-600`), User Messages (`bg-blue-500`), Model Responses (`bg-amber-500`), Tool Outputs (`bg-teal-500`), System Notifications (`bg-purple-500`), Unused Budget (`bg-muted`).

### 2.2 Stable Webview Insertion Anchors
| Anchor | Component | Selector | Surface Characteristics |
| :--- | :--- | :--- | :--- |
| **Header Bar** | `P6b` / `cascadeContext` | `header.cascade-header`, `div[data-testid="conversation-header"]` | Always pinned regardless of turn scroll depth |
| **Active Hook Banner** | `Qrb` / `Mrb` in `Xsb` (`main.js:8085`) | `div[data-testid="agent-loading"]` | Active-step visual focal point (`"Working"` / `"Compacting"`) |
| **Input Dock** | `t3b` / `v3b` | `div[data-testid="prompt-input-container"]` | Pre-submit budget inspection above/inside message input |

---

## 3. Standalone CLI (`agy`) Token & Compaction Formatting

Inspection of `/usr/bin/agy` confirmed three Go rendering routines (`google3/third_party/jetski/cli/`):
- `render/compaction_marker.go` (`render.renderCompactionMarker`): Inserts horizontal boundary divider labeled `Compacted`.
- `render.compactionStatsParts`: Computes token reduction using `CompactionTokens`, `ContextOverheadTokens`, and `compactionDuration`.
- `render.FormatTokens`: Renders `%s · %s/%s tokens\n (%.1f%%)` and `Base context: ~%d tokens (instructions: ~%d, tool definitions: ~%d)` sourced from `steps.CalculateTokenSums`.

---

## 4. Harness Surfacing & Calibrated Thresholds (ADR-033)

Early cleanroom experimentation mapped urgency tiers against the `CASCADE_USE_EXPERIMENT_CHECKPOINTER` `token_threshold = 50,000` constant; full production telemetry calibration under **ADR-033** subsequently aligned Agyis Harness runtime guards (`harness/hooks/token_proximity_guard.py` and `harness/hooks/pre_invocation_hook.py`) to the live `256,000`-token window:

| Runway Band | Token Threshold (Production ADR-033) | Enforcement & Surfacing Mechanism |
| :--- | :---: | :--- |
| **Nominal** | `< 180,000` | Silent in `PreToolUse` / `PreInvocation` |
| **Amber Runway Alert** | `180,000 – 229,999` | Proactive runway gauge in `token_proximity_guard.py` + `agyis status` |
| **Compaction Imminent** | `>= 230,000` (empirical avg `245,941`) | One-shot 40-line directive in `PreInvocation` (`psl-compaction-advisory`), subsequent 1-line badge, automatic checkpointing via `agyis checkpoint` |

GUI token HUD surfacing is implemented cleanly without modifying binary files via CDP injection (`agyis gui --hud` and `agyis gui --server`, complying with `PSL-INV-010` dynamic SPA `/c/:id` route synchronization and stale DOM purging on re-injection).
