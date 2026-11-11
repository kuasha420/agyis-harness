<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Google Antigravity Native Compaction Window Mechanisms
## Cleanroom Empirical Architecture Specification

**Document Identifier:** `REA-SPEC-ANTIGRAVITY-COMPACTION-2026-10-17`  
**Governing Standard:** ADR-028 / ADR-033 / Cleanroom Standards (`PSL-INV-007`)  
**Analysis Provider:** REA v6.5.0 (`go-build-info`, `sqlite`, `asar-dissect`, `v8-bundle-tracer`)  
**Target Architecture:** Google Antigravity v2.19.1 (Electron Shell + Jetski Cortex Language Server, CL `951519500`)  

---

## 1. System Overview & Immutable Evidence

Google Antigravity executes agentic trajectories through a packaged Electron host shell (`app.asar`) orchestrating an embedded Go language server (`language_server`, Jetski / Cortex) that serves the React frontend over loopback HTTPS. Trajectory compaction is a model-driven, structured checkpointing subsystem (`CortexStepCheckpoint`) managed by `CheckpointHandler` and `ContextSummaryHook`.

### Immutable Evidence Index

| Evidence ID | Subject Path | SHA-256 Digest | Provider / Engine | Scope & Relevance |
|:---|:---|:---|:---|:---|
| `ev_9a6fd366f2d157ce803cde...` | `/opt/Antigravity/resources/bin/language_server` | `2dce14e864bf5cb7fea8bdce56741570ce8a0efad00e9527224f0950d26ce891` | REA `inspect-go-binary` (Go 1.28 `cl/951519500`) | Core agent engine, cortex scheduler, checkpoint handler, HTTP/HTTPS web server |
| `ev_7b2e182eb1213cdf44aeb6...` | `/usr/bin/agy` | `ce1bdaed3201bb84f35d69d2773caec4f18af52af00e8c25f6cace07e4359615` | REA `inspect-go-binary` (Go 1.28 `cl/985595000`) | Standalone CLI client engine (`antigravity-cli 1.3.1`) |
| `ev_a74158469a14d3141c3dfb...` | `~/.gemini/antigravity/conversation_summaries.db` | `8a7476a5e0deac2e6607978c6bc8e0dee05368916dea08c6727e11c509c4a119` | REA `inspect-sqlite-database` (SQLite 3.53.4) | Global cross-session summary store, metadata catalog, and title cache |
| `ev_38fb29910d64a0280b271a...` | `/opt/Antigravity/resources/app.asar` | `9b36d0124ad1830119e7a6fcaeb34bfcfcf1daef50ecfa6067b8a7f9202a63d1` | REA `asar-dissect` | Electron host bridge (`hostBridgeServer.js`), process manager (`languageServer.js`) |
| `ev_10ce7489bb41094da55b70...` | `https://localhost:37277/main.js` | `3715c65f9737155e744a56a64be57da33ea7e64da4b10467b938fefcfeb1bbff` | REA `v8-bundle-tracer` | Frontend React client, active hook state tracker, "Compacting..." visual renderer |

---

## 2. Process & Component Topology

```text
Electron Host Shell (/opt/Antigravity/resources/app.asar)
 ├── dist/main.js              Window lifecycle coordinator
 ├── dist/hostBridgeServer.js  Loopback Connect-RPC bridge listener
 └── dist/languageServer.js    Spawns language_server on ephemeral HTTP/HTTPS ports
       │
       ▼
Jetski Cortex Language Server (/opt/Antigravity/resources/bin/language_server)
 ├── Embedded HTTPS/Web Server       Serves HTML, React main.js, Wasm at https://127.0.0.1:<port>/
 ├── cortex/executors/prehooks       ContextSummaryHook, CheckpointHook
 ├── cortex/handlers/checkpoint      CheckpointHandler, Summarizer
 ├── cortex/utils/truncator          TrajectoryTruncator
 ├── cortex/utils/utils              WaterFillAllocation
 └── tokenizer                       EstimateTokenCounter, ByteApproximationTokenCounter
       │
       ▼
React Frontend Client (https://127.0.0.1:<port>/main.js)
 ├── Mrb()                           Subscribes to activeHook ("context_summary")
 ├── Qrb()                           Renders <div data-testid="agent-loading"> state
 └── Jrb                             Maps "context_summary" -> "Compacting"
```

---

## 3. Compaction Triggers, Thresholds & Token Accounting

### 3.1 Trigger Modes
1. **Proactive Threshold (`MaybeCreateCheckpoint` / `shouldCheckpoint`)**: Evaluates trajectory consolidation once cumulative tokens reach configured threshold bounds.
2. **Reactive Budget-Breaker (`Checkpointing: no messages fit the executor budget`)**: Fires immediately when raw trajectory steps exceed the active model executor budget.
3. **Manual Operator Request (`manualCompactionRequested`)**: Triggered by explicit `/compact` command invocation.

### 3.2 `CheckpointConfig` & Experiment Bounds (`CASCADE_USE_EXPERIMENT_CHECKPOINTER`)

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

*Note: `token_threshold` (`50,000`) governs baseline checkpointer experiment configuration, whereas live full-context model limits (`max_token_limit: 256,000`) trigger production session compaction empirically around `245,941` average tokens (bounded by `ClampCheckpointConfigForModelInfo` / `ComputeSafeMaxTokenLimit`: `min(ConfiguredLimit, ModelContextLimit - ModelMaxOutputTokens)`).*

- **`MaxOverheadRatio` (`0.15`)**: Caps summary/metadata overhead at 15% of the active token budget.
- **`MovingWindowSize` (`1`)**: Retains recent uncompacted full-fidelity steps immediately preceding generation.

### 3.3 Token Accounting Hierarchy
1. **Authoritative Server Usage (`UsageMetadata`)**: `PromptTokenCount`, `CandidatesTokenCount`, `TotalTokenCount`, `ThoughtsTokenCount`, `CachedContentTokenCount`.
2. **Pre-Flight Local Estimator (`EstimateTokenCounter`)**: Non-blocking token count estimation when `ModelFeatures.SupportsEstimateTokenCounter` is enabled.
3. **Byte-Approximation Fallback (`ByteApproximationTokenCounter`)**: Sub-millisecond character/byte heuristic used by `DefaultSerializer.CountStepTokens`.
4. **Remote Multimodal Counter (`/google.ai.generativelanguage.v1main.GenerativeService/CountTokens`)**: `CountTokensRequest` for images, PDFs, and audio.

---

## 4. Compaction Algorithm, Storage & Pre-Invocation Injection

### 4.1 Model-Driven 6-Part Summarization
Executed by `CheckpointHandler` (`CHECKPOINT_STRATEGY_SAME_MODEL`, `use_last_planner_model: true`), emitting `<summary>...</summary>` containing:
1. Task Overview
2. Progress (completed milestones, file paths, artifacts, in-progress items)
3. Key Findings (constraints, rationale, resolved errors, abandoned approaches)
4. Active Context (hypotheses, external sessions, dependencies)
5. Next Steps (prioritized actions, blockers)
6. Commitments & Constraints

On model failure/timeout, `generateFallbackSummary` synthesizes a programmatic summary with `GetUsedFallbackSummary = true` and `GetModelSummarizationFailed = true`.

### 4.2 Water-Fill Allocation & Pruning
`GetWaterFillAllocation` packs context sections in priority tiers: (1) System prompt & instruction invariants, (2) Moving window verbatim steps (`moving_window_size`), (3) Captured user requests (`max_user_requests = 10`), (4) Artifact snapshots (`max_artifact_section_bytes`), and (5) `<CONTEXT_SUMMARY>`. Historical reasoning signatures are stripped (`WithSkipThoughtSignatureValidatorOnStrip`) and intermediate tool outputs are pruned via `TrajectoryTruncator`. The summary is injected as the final pre-invocation block (`context_summary_is_the_last_pre_invocation_hook`):

```xml
<CONTEXT_SUMMARY>
The following is a summary of the conversation history that has been truncated to fit within the context window:
<summary>...</summary>
</CONTEXT_SUMMARY>
```

### 4.3 Persistence Surfaces
1. **Per-Conversation SQLite (`~/.gemini/antigravity/conversations/<id>.db`)**: Inserts synthetic compaction checkpoint steps (`step_type = 23` in live v2.19+ databases; legacy `step_type = 4` in earlier captures) containing serialized `SessionSummary`, `CodeChangeSummary`, `IncludedStepIndexStart` / `IncludedStepIndexEnd`, `UserRequests`, `ArtifactSnapshots`, and `TrajectoryFileDiffs`, plus `checkpoint_index` in trajectory/executor metadata. Active context consumption per turn is carried in `UsageMetadata` (`input_tokens + cache_read_tokens`).
2. **Central Summary Store (`~/.gemini/antigravity/conversation_summaries.db`)**: Stores `raw_summary`, `step_count`, `last_modified_time`, and sidebar `preview`.
3. **Brain Directory (`~/.gemini/antigravity/brain/<id>/`)**: Preserves raw uncompacted outputs under `.system_generated/steps/<idx>/output.txt` alongside live artifacts (`implementation_plan.md`, `task.md`).

---

## 5. Internal Hook Contract & Frontend Status Rendering

### 5.1 `OnCompaction` Internal Protobuf (`hooks.proto` / `localharness.proto`)
- `CallHookRequest` field 9 carries `on_compaction_args: OnCompactionArgs { string interaction_id = 1; int64 step_index = 2; string summary = 3; }`.
- Expected response: `CallHookResponse.empty_result` or `error_message`. `OnCompaction` is strictly an **observational audit notification** and cannot mutate summaries or veto compaction.
- User-space tool output compaction in `agyis-harness` operates orthogonally via `PostToolUse` (`python3 -m harness.hooks.runner compactor`) at 2KB, deferring trajectory budget overflow ([empirical-baselines.md](../taxonomy/empirical-baselines.md): `39.69%` output volume / `21.31%` context reduction).

### 5.2 Frontend `"Compacting"` Indicator
`Jrb = { context_summary: "Compacting" }` maps `activeHook.hookName` inside React component `Mrb()`. `Qrb()` renders `<div data-testid="agent-loading">` showing `"Compacting"` when elapsed time `< 30s` and `"Compacting · <duration>"` when `>= 30s`, reverting to `"Working"` once the checkpoint step completes.

### 5.3 Epoch Continuity & Harness SSOT Synchronization (`ADR-035`)
- **Checkpoint Epoch Reset**: `harness/trajectory/` (`sqlite_reader.py`, `transcript_reader.py`, `health.py`) partitions every trajectory into discrete compaction epochs at each checkpoint step (`CHECKPOINT_STEP_TYPE = 23` in SQLite; `CHECKPOINT` in transcript steps), tracking both `total_steps` and active `epoch_steps` / `epoch_index` / `epoch_start_idx`.
- **Single-Source Readers**: `pre_invocation_hook.py`, `token_proximity_guard.py`, `harness/subagents/`, `agyis status`, and `harness/gui/trajectory_hud.py` consume `read_db_trajectory_state()` and `build_measured_breakdown()`, eliminating post-compaction step-count staleness, premature subagent retirement, and unattributed token masking.
