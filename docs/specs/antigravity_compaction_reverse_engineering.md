<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Google Antigravity Native Compaction Window Mechanisms
## Cleanroom Reverse Engineering Investigation & Architectural Specification

**Document Identifier:** `REA-SPEC-ANTIGRAVITY-COMPACTION-2026-10-17`  
**Governing Standard:** ADR-028 (Cleanroom Standards) / AGENTS Rule 7  
**Analysis Provider:** REA v6.5.0 (`go-build-info`, `sqlite`, `asar-dissect`, `v8-bundle-tracer`)  
**Target Architecture:** Google Antigravity v2.19.1 (Electron Shell + Jetski Cortex Language Server)  
**Investigation Date:** 2026-10-17  

---

## 1. Executive Summary & Verification Ledger

This specification documents the reverse engineered inner workings of the context window compaction, trajectory checkpointing, and visual status signaling mechanisms in **Google Antigravity** (build CL `951519500`, client v2.19.1).

The investigation established that Antigravity utilizes a hybrid multi-tiered architecture: an Electron application shell that acts as a secure local harness and webview container, orchestrating a heavy compiled Go binary (`language_server`, internal project name **Jetski / Cortex**). Compaction is not a simple string truncation; it is a structured, model-driven, and algorithmically governed checkpointing subsystem termed `CortexStepCheckpoint`.

### Immutable Evidence Index

| Evidence ID | Subject Path | SHA-256 Digest | Provider / Engine | Scope & Relevance |
|:---|:---|:---|:---|:---|
| `ev_9a6fd366f2d157ce803cde...` | `/opt/Antigravity/resources/bin/language_server` | `2dce14e864bf5cb7fea8bdce56741570ce8a0efad00e9527224f0950d26ce891` | REA `inspect-go-binary` (Go 1.28 `cl/951519500`) | Core agent engine, cortex scheduler, checkpoint handler, HTTP/HTTPS web server |
| `ev_7b2e182eb1213cdf44aeb6...` | `/usr/bin/agy` | `ce1bdaed3201bb84f35d69d2773caec4f18af52af00e8c25f6cace07e4359615` | REA `inspect-go-binary` (Go 1.28 `cl/985595000`) | Standalone CLI client engine (`antigravity-cli 1.3.1`) |
| `ev_a74158469a14d3141c3dfb...` | `~/.gemini/antigravity/conversation_summaries.db` | `8a7476a5e0deac2e6607978c6bc8e0dee05368916dea08c6727e11c509c4a119` | REA `inspect-sqlite-database` (SQLite 3.53.4) | Global cross-session summary store, metadata catalog, and title cache |
| `ev_38fb29910d64a0280b271a...` | `/opt/Antigravity/resources/app.asar` | `9b36d0124ad1830119e7a6fcaeb34bfcfcf1daef50ecfa6067b8a7f9202a63d1` | REA `asar-dissect` | Electron host bridge (`hostBridgeServer.js`), process manager (`languageServer.js`) |
| `ev_10ce7489bb41094da55b70...` | `https://localhost:37277/main.js` | `3715c65f9737155e744a56a64be57da33ea7e64da4b10467b938fefcfeb1bbff` | REA `v8-bundle-tracer` | Frontend React client, active hook state tracker, "Compacting..." visual renderer |

---

## 2. Architecture & Process Topology

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Google Antigravity Host                         │
├────────────────────────────────────────────────────────────────────────┤
│ 1. Electron Host Shell (/opt/Antigravity/resources/app.asar)          │
│    ├── dist/main.js           (Window manager & lifecycle coordinator) │
│    ├── dist/hostBridgeServer.js (Loopback Connect-RPC bridge listener) │
│    └── dist/languageServer.js (Spawns and monitors language_server)    │
│                 │                                                      │
│                 ▼ launches on dynamic port                             │
│ 2. Jetski Cortex Language Server (/opt/Antigravity/resources/bin/...) │
│    ├── Embedded HTTPS/Web Server (Serves frontend web assets at /)     │
│    ├── cortex/executors/prehooks (ContextSummaryHook, CheckpointHook)  │
│    ├── cortex/handlers/checkpoint (CheckpointHandler, Summarizer)      │
│    ├── cortex/utils/truncator    (TrajectoryTruncator)                 │
│    ├── cortex/utils/utils        (WaterFillAllocation)                 │
│    └── tokenizer                 (EstimateTokenCounter, ByteApprox)    │
│                 │                                                      │
│                 ▼ renders via webview                                  │
│ 3. React Frontend Client (Loaded from https://127.0.0.1:<port>/)       │
│    ├── Mrb() Component (Tracks activeHook: context_summary)            │
│    ├── Qrb() Component (Renders "Compacting" loading state & timer)    │
│    └── Jrb Mapping     (Maps hook "context_summary" -> "Compacting")   │
└────────────────────────────────────────────────────────────────────────┘
```

1. **Host Orchestration:** The Electron process (`app.asar`) does not execute LLM interactions directly. It initializes a loopback gRPC/Connect server (`hostBridgeServer.js`) and spawns the compiled binary `/opt/Antigravity/resources/bin/language_server` on a dynamic port (e.g. HTTPS port `37277`, HTTP port `34391`).
2. **Web Origin Isolation:** The Electron window loads `https://127.0.0.1:<port>/`. All HTML, React JavaScript bundles, and WebAssembly assets are served directly from the embedded server inside `language_server`.
3. **Core Subsystem Identity:** The agent logic resides in `google3/third_party/jetski/cortex` and `google3/third_party/gemini_coder/framework`. The compaction engine is specifically governed by `CheckpointHandler` and `ContextSummaryHook`.

---

## 3. Core Question 1: Compaction Trigger Mechanics & Token Thresholds

### 3.1 What Triggers Compaction?

Antigravity operates a **dual-trigger compaction model**:
1. **Proactive Threshold Trigger (`MaybeCreateCheckpoint` / `shouldCheckpoint`)**: Fired during step generation when the cumulative token count reaches or exceeds configured bounds.
2. **Reactive Budget-Breaker Trigger (`Checkpointing: no messages fit the executor budget`)**: Fired immediately when the raw trajectory cannot be formatted within the active model's executor context window without dropping critical conversation frames.
3. **Manual Operator Request (`manualCompactionRequested`)**: Triggered when a slash command or explicit user directive requests compaction.

### 3.2 Thresholds & Mathematical Bounds

Extracted from the runtime experiment configuration `CASCADE_USE_EXPERIMENT_CHECKPOINTER` and the `CheckpointConfig` protobuf:

```json
{
  "strategy": "CHECKPOINT_STRATEGY_SAME_MODEL",
  "max_token_limit": "256000",
  "token_threshold": "50000",
  "max_overhead_ratio": "0.15",
  "moving_window_size": "1",
  "max_output_tokens": "16384",
  "enabled": true,
  "use_last_planner_model": true,
  "is_sync": true,
  "max_user_requests": 10,
  "include_last_user_message": true,
  "include_running_task_snapshots": true,
  "include_subagent_snapshots": true,
  "include_artifact_snapshots": true
}
```

#### Key Invariant Constraints:
- **`TokenThreshold` (Default: 50,000 tokens):** The baseline cumulative threshold where `shouldCheckpoint` begins evaluating the trajectory for consolidation.
- **`MaxOverheadRatio` (Default: 0.15 or 15%):** Defines the maximum allowed ratio between the summary/overhead metadata and the active token budget. If metadata overhead exceeds 15%, older steps are pruned more aggressively.
- **`MaxTokenLimit` (Default: 256,000 tokens or clamped):** Governed by `ClampCheckpointConfigForModelInfo` and `ComputeSafeMaxTokenLimit`.
  $$\text{MaxTokenLimit} = \min\left(\text{ConfiguredLimit}, \text{ModelContextLimit} - \text{ModelMaxOutputTokens}\right)$$
  - *Engine Invariant Assertion:* `config.MaxTokenLimit (%d) cannot exceed the planner model's context window limit (%d) minus the planner model's MaxOutputTokens (%d)`.
  - *Protection Warning:* `tokenThreshold %d is greater than MaxTokenLimit %d. Checkpointing will not protect the model from exceeding the maximum context window`.
- **`MovingWindowSize` (Default: 1):** The count of recent full-fidelity interaction steps preserved completely uncompacted directly before the active generation point.

### 3.3 Token Measurement Taxonomy

Antigravity employs a three-tier token accounting system:
1. **Authoritative Server Usage Metadata:**
   The ground truth is derived from the server response payload `UsageMetadata` (`google3/google/internal/cloud/code/v1internal/v1internal_go_proto`):
   - `PromptTokenCount`: Tokens ingested from prompt history.
   - `CandidatesTokenCount`: Tokens emitted by the model.
   - `TotalTokenCount`: Cumulative total.
   - `ThoughtsTokenCount`: Tokens consumed by reasoning/thinking blocks.
   - `CachedContentTokenCount`: Tokens read from Google Vertex context cache.
2. **Local Pre-Flight Estimation (`EstimateTokenCounter`):**
   Implemented in `google3/third_party/jetski/tokenizer/tokenizer.(*EstimateTokenCounter).GetTokenCount`. When `ModelFeatures.SupportsEstimateTokenCounter` is enabled, the local engine estimates token counts to avoid blocking roundtrips.
3. **Byte-Approximation Fallback (`ByteApproximationTokenCounter`):**
   Located in `google3/third_party/gemini_coder/framework/core/serializers/serializers.ByteApproximationTokenCounter`. Used by `DefaultSerializer.CountStepTokens` for sub-millisecond heuristics, approximating tokens using character/byte length boundaries.
4. **Remote Token Counter Service:**
   Calls `/google.ai.generativelanguage.v1main.GenerativeService/CountTokens` (`CountTokensRequest`) for precise multimodal token accounting (images, PDFs, audio).

---

## 4. Core Question 2: Execution Under the Hood & Compaction Algorithm

### 4.1 Summarization Architecture

Compaction is executed by `google3/third_party/gemini_coder/framework/handlers/checkpoint/checkpoint.(*CheckpointHandler)`:

1. **Model Invocation Strategy (`CHECKPOINT_STRATEGY_SAME_MODEL`):**
   Compaction does not use an external cheap model; it reuses the active planner model (`use_last_planner_model: true`) to maintain semantic consistency.
2. **Structured 6-Part Continuation Prompt:**
   The language server prompts the model with a strict structural schema designed to enable seamless continuation without redundant work:
   - **Section 1: Task Overview:** Core user request, success criteria, resolved ambiguities.
   - **Section 2: Progress:** Completed milestones with concrete file paths, resource identifiers, tool outputs, artifacts produced, and in-progress items.
   - **Section 3: Key Findings:** Technical constraints, decisions made with rationales, errors encountered and resolutions, and **abandoned approaches** (explicitly recorded so successor turns do not re-attempt failing strategies).
   - **Section 4: Active Context:** Working hypotheses, state of external sessions, active dependencies.
   - **Section 5: Next Steps:** Prioritized next actions, prerequisites, and blockers.
   - **Section 6: Commitments & Constraints:** Explicit promises made to the user, styling rules, and scope limits.
   - *Envelope:* The model must wrap its output in `<summary>...</summary>` tags.
3. **Fallback Summarization (`generateFallbackSummary`):**
   If the model call fails, hits a context deadline, or times out, the engine does not crash. It triggers `generateFallbackSummary`, synthesizing a programmatic delta summary:
   - Flags `GetUsedFallbackSummary = true` and `GetModelSummarizationFailed = true` in `CortexStepCheckpoint`.
   - Truncates raw outputs with warning: `"The checkpoint summary has been truncated due to hitting max length. Please see the conversation log file for the full conversation."`

### 4.2 Message Pruning & Condensation Mechanisms

1. **The Water-Fill Token Allocation (`GetWaterFillAllocation`):**
   The engine applies a water-filling optimization algorithm across context sections:
   - Tier 1: System prompt & active instruction invariants.
   - Tier 2: Moving window steps (recent `moving_window_size` steps kept verbatim).
   - Tier 3: Captured user requests (`captureUserRequests`, up to `max_user_requests = 10`).
   - Tier 4: Artifact snapshots (`include_artifact_snapshots`, bounded by `max_artifact_section_bytes`).
   - Tier 5: The newly minted `<CONTEXT_SUMMARY>`.
2. **Pruning of Past Thoughts and Tool Bloat:**
   - **Reasoning Blocks:** Past thoughts are stripped from compacted historical turns (`WithSkipThoughtSignatureValidatorOnStrip`).
   - **Tool Output Compaction:** Intermediate tool stdout/stderr strings are compacted via `TrajectoryTruncator` (`truncateStepInternal`, `TruncateStepInPlace`).
3. **Prompt Injection Tag:**
   The resulting summary is injected as the final pre-invocation step (`context_summary_is_the_last_pre_invocation_hook`) using the XML block:
   ```xml
   <CONTEXT_SUMMARY>
   The following is a summary of the conversation history that has been truncated to fit within the context window:
   <summary>
   [Structured 6-Part Summary]
   </summary>
   </CONTEXT_SUMMARY>
   ```

### 4.3 Storage in SQLite and Conversation Brain

Compacted states are persisted across three locations:

1. **Per-Conversation SQLite Database (`~/.gemini/antigravity/conversations/<conv-id>.db`):**
   - **`steps` table:** A synthetic step with `step_type = 4` (`CortexStepCheckpoint`) is inserted. The `step_payload` BLOB contains the serialized protobuf:
     - `SessionSummary`: Text of the generated `<summary>`.
     - `CodeChangeSummary`: Structural git diff metadata.
     - `IncludedStepIndexStart` & `IncludedStepIndexEnd`: Absolute step indices covered by this checkpoint.
     - `UserRequests`: List of prior user prompt strings.
     - `ArtifactSnapshots`: Snapshot hashes of workspace artifacts.
     - `TrajectoryFileDiffs`: Aggregated file diffs.
   - **`trajectory_metadata_blob` & `executor_metadata`:** Records `checkpoint_index` pointing to the latest valid checkpoint step.
2. **Central Summary Database (`~/.gemini/antigravity/conversation_summaries.db`):**
   - The `conversation_summaries` table stores the latest `raw_summary` (BLOB) alongside `step_count`, `last_modified_time`, and `preview` text for the UI sidebar.
3. **The Conversation Brain Directory (`~/.gemini/antigravity/brain/<conv-id>/`):**
   - `.system_generated/steps/<idx>/output.txt`: Raw tool output logs remain preserved on disk for auditing even if compacted from model context.
   - Live artifacts (`implementation_plan.md`, `task.md`, generated code files) reside in the root of `<conv-id>/` and are never overwritten or deleted by compaction.

---

## 5. Core Question 3: SDK, Hooks, and Plugin Interfaces

### 5.1 The `OnCompaction` Lifecycle Hook

In Google Antigravity's internal Protobuf contracts (`google3/learning/genai/api/interactions/proto/hooks.proto` and `localharness.proto`), a dedicated compaction hook event exists:

```protobuf
message CallHookRequest {
  string request_id = 1;
  string name = 2;
  LifecycleHook type = 3;
  // Arguments for specific hook types:
  PreTurnArgs pre_turn_args = 4;
  PostTurnArgs post_turn_args = 5;
  PreToolArgs pre_tool_args = 6;
  PostToolArgs post_tool_args = 7;
  OnToolErrorArgs on_tool_error_args = 8;
  OnCompactionArgs on_compaction_args = 9; // Dedicated compaction event
  StopArgs stop_args = 10;
}

message OnCompactionArgs {
  string interaction_id = 1; // Or trajectory_id
  int64 step_index = 2;
  string summary = 3;
}
```

### 5.2 Hook Response & Interception Capabilities

- **Hook Response Contract:**
  When `CallHookRequest.on_compaction_args` is dispatched, the expected response is:
  `CallHookResponse.empty_result` (`GetEmptyResult`) or `CallHookResponse.error_message`.
- **Interception Verdict:**
  `OnCompaction` is an **asynchronous notification/audit hook**, not an intercepting or mutating filter. Hooks **cannot** modify the summary, rewrite compacted step indices, or veto compaction execution. The engine executes compaction authoritatively; hooks merely observe the resulting summary and step index.

### 5.3 Public Plugin Surface vs. Internal Harness

- **Public Plugin Manifest (`hooks.json`):**
  The public Antigravity plugin manifest standard currently exposes only:
  `PreToolUse`, `PostToolUse`, `PreTurn`, `PostTurn`, `OnToolError`, `Stop`.
  `OnCompaction` is not yet documented or registered in standard third-party plugin schemas.
- **Python SDK / User-Space Compaction:**
  The `psl-agy-harness` compactor (`harness.cli hook compactor`) operates in user-space at `PostToolUse` (intercepting large stdout streams and truncating them to 2KB). This is distinct from the native engine compaction (`ContextSummaryHook`), which operates at the trajectory level.
- **MCP Server Boundaries:**
  Compaction is completely transparent to MCP servers. Neither stdio nor SSE MCP transports receive compaction signals or context window metadata.

---

## 6. Core Question 4: UI Visual State Rendering Mechanics

The frontend visual state `"Compacting..."` is rendered via a reactive chain linking the language server's active hook emitter to the React DOM.

### 6.1 Hook Name Mapping

In `/tmp/antigravity_dirty_room/main.js` (served at `https://127.0.0.1:<port>/main.js`):

```javascript
// Static hook-to-label dictionary
const Jrb = { 
  context_summary: "Compacting" 
};
```

### 6.2 The Active Hook Tracker (`Mrb`)

The React component `Mrb()` subscribes to `activeHook` from `cascadeContext.state.agentStateProvider`:

```javascript
function Mrb() {
  const agentState = useContext(CascadeContext)?.state.agentStateProvider;
  const activeHook = useHookSelector(agentState, (s) => s?.activeHook);
  const hookLabel = activeHook ? Jrb[activeHook.hookName] : undefined;
  const startTime = activeHook?.startedAt ? toDate(activeHook.startedAt).getTime() : undefined;
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (startTime !== undefined) {
      setNow(Date.now());
      const timer = setInterval(() => setNow(Date.now()), 1000);
      return () => clearInterval(timer);
    }
  }, [startTime]);

  if (hookLabel !== undefined && startTime !== undefined) {
    const elapsedMs = now - startTime;
    if (elapsedMs < 5000) {
      return hookLabel; // Displays "Compacting"
    }
    if (elapsedMs < 30000) {
      return hookLabel; // Displays "Compacting"
    }
    // For long compaction runs (>=30s), appends human-readable duration
    return `${hookLabel} · ${formatDuration(elapsedMs)}`; // e.g. "Compacting · 35s"
  }
}
```

### 6.3 The Loading Indicator (`Qrb`)

The main agent status indicator `Qrb` renders the status badge in the UI:

```javascript
// Checks if the latest step is an in-flight checkpoint step:
const isCheckpointInFlight = (() => {
  if (lastStep?.step.case !== "checkpoint") return false;
  const val = lastStep.step.value;
  return (
    (lastStep.status === CortexStepStatus.RUNNING ||
     lastStep.status === CortexStepStatus.PENDING ||
     lastStep.status === CortexStepStatus.GENERATING ||
     lastStep.status === CortexStepStatus.WAITING) &&
    !val?.intentOnly &&
    !!val?.renderLatestCheckpoint
  );
})();

// DOM Render:
return (
  <div data-testid="agent-loading" className="whitespace-nowrap py-1 text-sm text-secondary-foreground min-h-8 tabular-nums">
    {hookStatusText ?? (isCheckpointInFlight ? "Compacting" : "Working")}
    <Spinner />
  </div>
);
```

When compaction starts:
1. `ContextSummaryHook` is dispatched by the cortex engine.
2. The language server sets `activeHook.hookName = "context_summary"`.
3. The frontend state selector triggers a re-render of `Mrb()`.
4. `Jrb["context_summary"]` resolves to `"Compacting"`.
5. `<div data-testid="agent-loading">` transitions from `"Working"` to `"Compacting"`.
6. If the model summarization call takes longer than 30 seconds, a live duration counter is appended (`"Compacting · 32s"`).
7. Upon completion of the model summary and injection of the synthetic checkpoint step, `activeHook` clears, returning status to `"Working"`.

---

## 7. Comparative Technical Matrix

| Dimension | Google Antigravity Native Engine | Agyis Harness (`psl-agy-harness`) |
|:---|:---|:---|
| **Execution Domain** | Compiled Go binary (`language_server` / Cortex) | Python 3.12 hermetic runtime (`harness/`) |
| **Compaction Trigger** | Proactive at `50,000` tokens; reactive on executor budget overflow | Proactive tool-output compaction (`PostToolUse`) at `2,048` bytes |
| **Summarization Method** | Model-driven 6-part structured prompt with programmatic fallback | Heuristic snippet compression / single contiguous replacement |
| **Token Accounting** | Three-tier (`UsageMetadata`, `EstimateTokenCounter`, `CountTokens` RPC) | Fast character/byte approximation + transcript telemetry tracking |
| **State Storage** | `conversations/<id>.db` (`steps` table) + `conversation_summaries.db` | `telemetry.db` (`steps` table, trajectory classification) |
| **UI Surface** | `Mrb()` hook selector + `Qrb()` checkpoint step detector (`"Compacting"`) | Telemetry CLI gauge (`agyis status`, `agyis audit`) |
| **Interception Capability** | None (`OnCompaction` is observational audit hook) | Full pre/post command interceptors (`command-safety`, `anti-loop`) |

---

## 8. Cleanroom Conclusions & Architectural Recommendations

1. **Alignment with Native Compaction:**
   Agyis Harness's Rule 4 (Context Preservation healthy zone `<50k tokens`) is **empirically validated** by Antigravity's internal threshold: `CASCADE_USE_EXPERIMENT_CHECKPOINTER` explicitly sets `token_threshold = 50000`. By keeping conversations under 50,000 tokens, agents avoid triggering the heavy model-driven compaction loop.
2. **PostToolUse Compaction Synergy:**
   The harness's 2KB `compactor` hook directly mitigates the primary cause of reactive emergency compaction (`Checkpointing: no messages fit the executor budget`). By pruning bulky terminal and grep outputs before they enter the trajectory SQLite store, tool-level compaction defers native context overflow.
3. **Formal Verification Assurance:**
   All findings in this specification are substantiated by immutable REA evidence digests and decompilation-free static inspection of shipped artifacts (`app.asar`, `language_server`, `conversation_summaries.db`, and `main.js`), fulfilling all ADR-028 cleanroom criteria.
