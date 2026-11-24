<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Official Lifecycle Hooks Specification (`hooks.json`)

## Overview
Antigravity lifecycle hooks allow execution of external shell commands synchronously at deterministic transition points in the agent loop. Hooks are declared in `hooks.json` at:
- **Workspace root**: `.agents/hooks.json` (or `.agent/hooks.json`)
- **Plugin bundles**: `<plugin_dir>/hooks.json`
- **Global user root**: `~/.gemini/config/hooks.json`

Top-level keys are arbitrary unique hook names with an optional `"enabled": false` kill-switch. Handlers across layers merge sequentially in discovery order; `command` performs `~` expansion with process `cwd` pinned to the directory containing `hooks.json`, defaulting to a `30`s native timeout (`5`s in `agyis-harness`).

---

## 1. Event Types & Topologies (Flat vs. Grouped Matcher)

Antigravity supports **6** lifecycle events across two schema layouts (`matcher` regex is supported only on tool events; `~` and tool stripping convert internal names like `CORTEX_STEP_TYPE_RUN_COMMAND` $\to$ `run_command`):

| Event | Layout Topology | Matcher Key | Ingress Extensions (above common fields) | Expected Egress (`stdout`) |
| :--- | :--- | :--- | :--- | :--- |
| `SessionStart` | **Flat** list | Ignored | Common fields | `{"injectSteps": [...]}` |
| `PreToolUse` | **Grouped** `{matcher, hooks}` | Yes (`"<regex>"`) | `toolCall: {name, args}`, `stepIdx` | `{"decision": "allow"\|"deny"\|"ask"\|"force_ask", "reason": "...", "overwrite": {...}, "permissionOverrides": [...]}` |
| `PostToolUse` | **Grouped** `{matcher, hooks}` | Yes (`"<regex>"`) | `toolCall: {name, args}`, `stepIdx`, optional `error` | **`{}`** or **`{"overwriteResult": "<compacted>"}`** *(compactor overwrites `>2KB` succeeding `run_command` and `>32KB` `read_file`/`view_file` while keeping errors verbatim `{}`; returning `{"decision": "allow"}` triggers warnings)* |
| `PreInvocation` | **Flat** list | Ignored | `invocationNum`, `initialNumSteps` | `{"injectSteps": [...]}` |
| `PostInvocation` | **Flat** list | Ignored | `invocationNum`, `initialNumSteps` | `{"injectSteps": [...], "terminationBehavior": "force_continue"\|"terminate"\|""}` |
| `Stop` | **Flat** list | Ignored | `executionNum`, `terminationReason`, `error`, `fullyIdle` | `{"decision": "continue"\|"allow", "reason": "..."}` |

---

## 2. JSON I/O Contracts (Strict camelCase Protojson)

### Common Payload Metadata (Sent on `stdin`)
All payloads use strict camelCase keys:
```json
{
  "conversationId": "270b7abc-9b59-4f50-9c49-de3ed7e04f06",
  "workspacePaths": ["/workspace/agyis-harness"],
  "transcriptPath": "~/.gemini/antigravity/brain/.../transcript.jsonl",
  "artifactDirectoryPath": "~/.gemini/antigravity/brain/.../",
  "modelName": "auto"
}
```

### `PreToolUse` Decision & Shallow `overwrite` Schema (`stdout`)
```json
{
  "decision": "allow",
  "reason": "Detailed justification for the decision.",
  "overwrite": {
    "CommandLine": "normalized-command"
  },
  "permissionOverrides": ["command(...)"]
}
```
- `"force_ask"` bypasses cached `"Always Allow"` grants.
- `"overwrite"` performs a shallow top-level key replacement on `args` and prefixes the tool result with `[Notice: Hook rewrote tool arguments for keys: ...]`.

### `injectSteps` Envelope & Nested `systemMessage` Contract
`SessionStart`, `PreInvocation`, and `PostInvocation` inject steps via `"injectSteps"`:
- **`systemMessage`** *(required in `agyis-harness`)*: **MUST use a nested dictionary** (`{"systemMessage": {"systemMessage": "...", "metadata": {}}}`); passing a raw string fails protojson decoding. All `pre_invocation_hook.py` advisories (role pinning, `80`-step epoch horizon nudges, and compaction alerts) emit nested `systemMessage` exclusively.
- **`userMessage`** *(persistent synthetic user turn)*: plain string -> `{"userMessage": "..."}`.
- **`ephemeralMessage`** *(deprecated legacy variant)*: previously used for transient nudges, **never emitted** by `agyis-harness` (`v2.34.0+` hooks standardize on nested `systemMessage`).

### `Stop` Ingress (`terminationReason`) & 2-Block Safety Valve
`Stop` ingress includes `fullyIdle` (background `manage_task` completion) and `terminationReason` (`ExecutorTerminationReason` stripped enum across **9** values):
- `NO_TOOL_CALL`, `MAX_INVOCATIONS`, `MAX_FORCED_INVOCATIONS`, `MAX_TOKEN_BUDGET_EXCEEDED`, `ERROR`, `USER_CANCELED`, `TERMINAL_STEP_TYPE`, `TERMINAL_CUSTOM_HOOK`, `INJECTED_RESPONSE`.

Returning `{"decision": "continue", "reason": "..."}` blocks termination and re-enters the loop. After **2** consecutive blocks (`block_count >= 2`), the `agyis-harness` anti-deadlock safety valve returns `"decision": "allow"` with a warning.

---

## 3. Reference Implementation: `agyis-harness` Hooks

`hooks.json` registers **7** named hook blocks dispatching **7** Python hook modules via `python3 -m harness.hooks.runner <name>` across **8** verified hook check slots (`psl-stop-verification-fence` registers both `verification-fence` on `PreToolUse`/`Stop` and `post-verification-fence` on `PostToolUse`, so `doctor.py` / `hygiene_checks.py` verifies 8 command entries across the 7 blocks). Ephemeral state caches default to `/tmp/agyis_harness_state_{uid}` (overridable via `AGYIS_HARNESS_STATE_DIR` / `PSL_HARNESS_STATE_DIR`):

1. `command_safety_hook.py` (`psl-command-safety-guard`): PreToolUse shell sanitizer (`run_command`, `manage_task`, `swarm`, `run_workflow`, `call_mcp_tool`, `mcp_.*`), Python >= 3.12 runtime injector, eager/lazy MCP normalization, `/swarm` pause guard, SSH timeouts, and grep/diff exit normalizer (ADR-013).
2. `anti_loop_hook.py` (`psl-anti-loop-guard`): PreToolUse repetitive call breaker across canonical `v2.34+` and alias tools (`read_file`, `write_file`, `edit_file`, `run_command`, `swarm`, `run_workflow`, `read_board`, `manage_task`), Issue #41 `manage_task(Action='status')` advisory allow, `.system_generated/{tasks,logs}/` log-polling Exit 2 deny, and non-blocking `SOFT_EPOCH_STEP_ADVISORY` (`80` epoch steps) horizon advisory.
3. `output_compactor_hook.py` (`psl-output-compactor`): PostToolUse deterministic compactor emitting `{"overwriteResult": compacted}` for succeeding `>2KB` `run_command` and `>32KB` `read_file`/`view_file` outputs while returning `{}` on errors (`exitCode != 0` / `error`) or smaller outputs, with DEF-04 character pre-slicing (`>200KB`).
4. `completion_fence_hook.py` (`psl-stop-verification-fence` -> `verification-fence` + `post-verification-fence`): PreToolUse/PostToolUse/Stop fence with decoupled dirty state (`code_dirty` vs `spec_dirty`).
5. `token_proximity_guard.py` (`psl-token-proximity-guard`): PreToolUse SQLite URI monitor decoding protobuf token gauges scaled across `256k` / **Gemini 4 (`gemini-4-neon`, `gemini-4-hydrogen`) `512k`** / `1M` windows (`70%` amber / `90%` red).
6. `anti_drift_hook.py` (`psl-anti-drift-guard`): PreToolUse plan adherence guard, Plan-Mode code lock (ADR-031A), Auditor write-block, and Q5 read-only shell mutation guard.
7. `pre_invocation_hook.py` (`psl-compaction-advisory`): PreInvocation dynamic attention runway evaluator and role-anchored nested `systemMessage` compaction advisory (ADR-033, ADR-035).

### 3.1 The `psl-stop-verification-fence` Contract (ADR-022 / ADR-028)

The `psl-stop-verification-fence` hook enforces verification discipline by preventing agents from declaring completion when code or cleanroom specifications have been modified without formal verification.

#### A. Triple Event Registration in `hooks.json`
```json
{
  "psl-stop-verification-fence": {
    "PreToolUse": [
      {
        "matcher": "write_file|edit_file|create_file|insert_edit_into_file|write_to_file|replace_file_content|multi_replace_file_content|run_command|execute_command|bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 -m harness.hooks.runner verification-fence",
            "timeout": 5
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "write_file|edit_file|create_file|insert_edit_into_file|write_to_file|replace_file_content|multi_replace_file_content|run_command|execute_command|bash|call_mcp_tool|mcp_.*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 -m harness.hooks.runner post-verification-fence",
            "timeout": 5
          }
        ]
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "python3 -m harness.hooks.runner verification-fence",
        "timeout": 5
      }
    ]
  }
}
```

#### B. Operational State Machine & Decoupled Dirty State (ADR-028)

The completion fence decouples dirty state into two independent flags:

1. **`code_dirty` State**:
   - Set when any file matching `CODE_EXTENSIONS` (`.py`, `.ts`, `.rs`, `.go`, `.c`, `.sh`) outside specification directories is modified.
   - Cleared ONLY when the active repository test runner (`agyis test`, `pytest`, `npm test`, `cargo test`) runs and exits with code 0.
   - When active, blocks agent `Stop` with:
     `Verification Required: Unverified code edits detected in: <files>. Execute 'agyis test' (or 'python3 -m harness.cli test') before stopping.`

2. **`spec_dirty` State**:
   - Set when cleanroom contracts (`docs/specs/**`, `.agents/ledger/**`) with declarative extensions (`.md`, `.json`, `.yaml`, `.proto`, `.schema`) are modified.
   - Does NOT demand unit tests!
   - Cleared when `agyis verify --spec` exits 0, or when cleanroom manifest is verified via `rea verify-reconstruction` / MCP `verify_reconstruction`.
   - When active, blocks agent `Stop` with:
     `Cleanroom Verification Required: Unverified cleanroom contract edits detected in: <files>. Execute 'rea verify-reconstruction' or 'agyis verify --spec' before stopping.`

3. **Code-in-Specs Dual Dirty Guard (DEF-01)**:
   - If an agent writes executable code (`.py`, `.ts`, `.sh`) into `docs/specs/`, the fence sets **BOTH `code_dirty = True` and `spec_dirty = True`**, preventing agents from evading unit test requirements.
   - When active alongside code changes, blocks agent `Stop` with:
     `Verification Required: Unverified code and cleanroom contract edits detected in: <files>. Execute 'agyis test' (or 'python3 -m harness.cli test') before stopping.`

4. **Ephemeral Scratch Paths**:
   - Ephemeral scratch paths (`.rea/**`, `decompiled/**`, `artifacts/rea/**`, `/scratch/`, or temporary paths outside workspace root) never mark state dirty.

5. **Formal Ledger & Manifest Clearance (DEF-06)**:
   - `is_manifest_verified()` (`harness/hooks/fence_classifiers.py`) prioritizes `.agents/ledger/obligation_ledger.json` via `validate_obligation_ledger()` (`harness/cleanroom/obligation.py`, `REA 6.9.0` strictObject schema: checking `evidence_bundle`, non-empty `reviewed_obligations` with `disposition` in `{"active", "blocked", "out-of-scope"}`, and `manifest.bindings` list with empty/resolved `contradictions`).
   - Falls back to legacy `.agents/ledger/manifest.json` (`status: "verified"`, 64-character lowercase SHA-256 `evidence_hash`, and non-empty `obligations` where all entries are `"satisfied"`). Passing clears `spec_dirty = False` automatically.

6. **Anti-Deadlock Safety Valve**:
   - If blocked twice consecutively (`block_count >= 2`), the safety valve trips and allows termination with warning (`"decision": "allow"`), preventing infinite loops.

7. **Verification Clearance via Test Runner / Verify Command**:
   - Running `./agyis test` (or `python3 -m harness.cli test`) clears `code_dirty = False` and `spec_dirty = False`.
   - Running `agyis verify --spec` or `rea verify-reconstruction` clears `spec_dirty = False` without requiring test suite execution.

### 3.2 The `psl-token-proximity-guard` Contract (ADR-014 / ADR-028 / ADR-033 / ADR-035)

The token proximity guard monitors active session context accumulation proportionally across the active model window (`CONTEXT_WINDOW_TOKENS = 256_000` baseline, scaling automatically to **Gemini 4 (`gemini-4-neon`, `gemini-4-hydrogen`) `512k`** and **`1M`** windows at `~70%` amber / `~90%` red).

#### A. Registration in `hooks.json`
```json
{
  "psl-token-proximity-guard": {
    "PreToolUse": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 -m harness.hooks.runner token-proximity",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

#### B. Decoding & Thresholds (`harness.trajectory` SSOT)
1. **SSOT Delegation (`harness.trajectory`)**: Delegates read-only SQLite access (`file:<path>?mode=ro`), protobuf decoding, epoch splitting, and burn-rate velocity to `read_db_trajectory_state()` (`harness/trajectory/sqlite_reader.py`), sharing a bounded locked-CID backoff cache (`MAX_LOCKED_CIDS = 256`, `LOCK_EXPIRY_SECONDS = 2.0`).
2. **Authoritative Token Sum & Epoch Barriers**: Decodes binary protobuf `UsageMetadata` via `input_tokens + cache_read_tokens` (`ProtobufUsageMetrics.total_prompt_tokens`) and bounds epoch token and step accounting to steps following the latest compaction checkpoint (`CHECKPOINT_STEP_TYPE = 23` / transcript `CHECKPOINT`).
3. **Dynamically Scaled Thresholds (`get_scaled_thresholds`)**: Scales the `256,000`-token baseline (`AMBER_THRESHOLD = 180_000`, `RED_THRESHOLD = 230_000`) proportionally against the active model's detected context window (`128k`–`1M`, e.g., `512k` Gemini 4 -> `360k` amber / `460k` red):
   - `< amber_threshold`: Silent (nominal operation within healthy runway).
   - `amber_threshold .. red_threshold - 1`: Emits an ANSI amber warning gauge + `tok/min` burn rate to `stderr`.
   - `>= red_threshold`: Emits a bold ANSI red alert and terminal bell (`\a`) synchronized with §3.6 `psl-compaction-advisory`.
4. **Fail-Open Invariant**: Always outputs `{"decision": "allow"}` and exits 0. Tool calls are never interrupted.


### 3.3 Command Safety & Subshell PATH Reliability Contract (ADR-023)

The `command_safety_hook.py` hook intercepts `run_command` in `PreToolUse` to guarantee reliable subshell execution:

#### A. User-Space Toolchain PATH Shim Recovery
- **Problem**: Non-login subshells (`bash -c "..."`) spawned by agent execution do not source user dotfiles (`~/.bashrc`, `~/.profile`), leading to Exit 127 ("command not found") for user-space binaries.
- **Discovery**: `get_user_path_shims()` dynamically discovers candidate user toolchain directories if they exist on the host:
  `~/.local/bin`, `~/.cargo/bin`, `~/.local/share/pnpm`, `~/.pyenv/shims`.
- **Injection**: When a command invokes user toolchains (`uv`, `pnpm`, `npm`, `npx`, `cargo`, `rustc`, `pytest`, `ruff`, `black`, `mypy`, `flake8`, `tsc`) and `PATH=` is not already defined, `inject_path_shims()` prepends:
  ```bash
  export PATH="<discovered_shims>:$PATH"; <cmd>
  ```
- **Idempotency**: If `PATH=` or user-space paths are already present in the command string, no modification is performed.

#### B. Network Probe Timeout Injection
- **Problem**: Standalone `ssh` calls to unreachable or offline mesh nodes hang indefinitely, causing agent background tasks to stall.
- **Injection**: When `ssh` is invoked without explicit timeout configuration, `inject_ssh_timeouts()` injects non-blocking options:
  ```bash
  -o ConnectTimeout=5 -o BatchMode=yes -o ServerAliveInterval=2 -o ServerAliveCountMax=2
  ```
- **Idempotency**: If `ConnectTimeout` is already defined, the command is left untouched.

#### C. Preserved Invariants
- Hard-blocks dangerous patterns (`rm -rf /`, `mkfs`, `dd`).
- Hard-blocks interactive TUI commands (`nano`, `vim`, `less`, etc.).
- Enforces non-interactive pagers (`PAGER=cat` for `git`, `gh`) and `export PATH="<shims>:$PATH"; <cmd>` syntax safe around shell keywords.
- Injects certified CPython 3.12+ for genuine multi-line inline scripts (`python3 -c`, `node -e`, `bash -c`, `sh -c`) and resolves verified `workspacePaths` scratch targets while preserving short pipelines and quoted strings.
- Surgical tail sanitization (`|| [ $? -eq 1 ]`) for standalone pattern searches (`grep`, `diff`).

#### D. Anti-Loop & Reactive Wait Enforcement (`anti_loop_hook.py`, Issue #41)
`psl-anti-loop-guard` intercepts `read_file|view_file|grep_search|list_dir|find_by_name|run_command|manage_task|swarm|run_workflow|read_board|write_file|edit_file|...` in `PreToolUse` with per-session sliding-window tracking persisted in `/tmp/agyis_harness_state_{uid}`:
- **`manage_task(Action='status')` Non-Blocking Advisory (Issue #41)**: Returns `{"decision": "allow", "reason": "Advisory: Background tasks notify reactively upon exit. Avoid polling status to conserve steps."}` rather than hard-blocking interactive inspection.
- **Background Log Polling Deny**: Repeated inspection of `.system_generated/tasks/` or `.system_generated/logs/` via `read_file`/`view_file`, `grep_search`, or shell readers (`tail`, `cat`) triggers `"decision": "deny"` (Exit 2), enforcing reactive wakeup.
- **Cleanroom Spec & Verification Reset**: Code edits reset test verification counters, while `docs/specs/**` / `.agents/ledger/**` use an elevated sliding window quota (`SPEC_WINDOW_MAX_CALLS = 8`) while still denying `>= 3` consecutive identical calls.
- **Soft Epoch Horizon Advisory (`Issue #109`)**: Emits a non-blocking stderr advisory under `deep_execution` roles once active-epoch steps reach `SOFT_EPOCH_STEP_ADVISORY` (`80`), encouraging targeted symbol lookups without blocking execution.
### 3.4 Plan-to-Execution Anti-Drift Verification Gate (ADR-024)

The `anti_drift_hook.py` hook (`psl-anti-drift-guard`) intercepts file modifications, shell mutations, and orchestrations in `PreToolUse` to ensure agents do not mutate files outside the approved implementation plan or violate role boundaries.

#### A. Registration in `hooks.json`
```json
{
  "psl-anti-drift-guard": {
    "PreToolUse": [
      {
        "matcher": "write_file|edit_file|create_file|insert_edit_into_file|write_to_file|replace_file_content|multi_replace_file_content|run_command|invoke_subagent|swarm|run_workflow",
        "hooks": [
          {
            "type": "command",
            "command": "python3 -m harness.hooks.runner anti-drift",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

#### B. Plan Discovery & Boundary Extraction
1. **Plan Discovery (`find_active_plan`)**:
   - Searches `PSL_PLAN_PATH` environment variable override.
   - Searches workspace root: `.agents/artifacts/implementation_plan.md`, `implementation_plan.md`, `phase_*_plan.md`.
   - Searches current working directory and walks parent worktrees.
   - Searches active conversation brain directory (`~/.gemini/antigravity/brain/<conv_id>/`).
2. **Boundary Parsing (`parse_plan_files`)**:
   - Extracts targets from markdown links (`[basename](file:///path/to/file)` or relative links).
   - Extracts targets from action headers (`#### [MODIFY] <markdown-file-link>`, `#### [NEW] path/to/file`, `#### [DELETE] ...`).
   - Extracts targets from backticks (` `path/to/file.py` `), excluding tool names, commands, keywords, and flags.
   - Indexes full paths, relative subpaths, and basenames for multi-resolution matching.

#### C. Exemption Model (`is_exempt_file`)
Non-code and operational files are never blocked by the anti-drift gate:
- Markdown documentation (`.md`, `.markdown`).
- Text documentation (`.txt`, `.rst`, `.adoc`).
- Artifact directories (`.agents/artifacts/*`, brain directories).
- Temporary scratch files (`scratch/*`, `tmp/*`, `/tmp/*`).

#### D. Decision Matrix (`check_drift`)
- **Exempt / In-Plan**: Emits `{"decision": "allow"}`.
- **Unconstrained (no plan or empty declared files)**: Emits `{"decision": "allow"}`.
- **Undeclared Edit (Non-Strict Mode, Default)**: Emits:
  ```json
  {
    "decision": "allow",
    "reason": "PSL Anti-Drift Notice: Target file '<file>' was not declared in implementation_plan.md; permitted under non-strict mode."
  }
  ```
- **Undeclared Edit (Strict Mode, `PSL_STRICT_ANTI_DRIFT=1` or `strict=True`)**: Emits:
  ```json
  {
    "decision": "ask",
    "reason": "PSL Anti-Drift Gate: Target file '<file>' is not listed in implementation_plan.md. Please confirm intentional edit."
  }
  ```

---

### 3.5 PreToolUse Auditor Write-Block Guard & Zero-Token Context Health Gauge (ADR-025)

* **Hook Name**: `anti-drift` (auditor write-block extension) & `harness.subagents`
* **Trigger Event**: `PreToolUse` (interception) and programmatic telemetry
* **File Location**: `harness/hooks/anti_drift_hook.py`, `harness/subagents/`

#### A. Auditor Permissions Paradox & Write-Block Guard
In the PSL Subagent Ladder protocol, the **Auditor** (`agyis_auditor`) requires command execution privileges (`run_command`) to run automated tests and doctor diagnostics, but must never mutate source files or test fixtures. Because granting platform execute permissions often surfaces editing tools in the agent's environment, `check_auditor_write_block()` enforces a deterministic software fence in `PreToolUse`.

- **Interception Trigger**: Tool call is `write_file`, `edit_file` (or legacy `write_to_file`, `replace_file_content`, `multi_replace_file_content`), OR a mutating `run_command` shell command caught by the Q5 shell mutation guard (`_is_mutating_shell_command`), AND calling agent role is `agyis_auditor`, `agyis_reviewer`, `agyis_planner`, `agyis_coordinator`, or `agyis_investigator` (on product files).
- **Response Contract**:
  ```json
  {
    "decision": "deny",
    "reason": "PSL Auditor Invariant: agyis_auditor is strictly verification-only and cannot mutate files."
  }
  ```
- **Allowed Tools**: Read and command execution tools (`run_command`, `read_file`, `manage_task`, `send_message`, `read_board`, `post_message`, `search_web`) remain available for hermetic verification.

#### B. Zero-Token Context Estimator & Health Gauge
`estimate_subagent_context()` calculates subagent context consumption, step depth, and health status in microseconds with zero LLM API token overhead:
- **Transcripts $\le 2\text{ MB}$**: Exact line-by-line streaming parser extracting exact steps, characters, and explicit token telemetry in $<1.5\text{ ms}$.
- **Titan Transcripts $> 2\text{ MB}$**: Fast size-heuristic fallback estimating token volume and step depth in $<0.1\text{ ms}$ without loading titan payloads into RAM.
- **Window-Scaled Health Zones** (`256k` baseline; scales proportionally for Gemini 4 `512k`/`1M` models):
  - 🟢 **HEALTHY** (`<65%` window fill AND `<80` active-epoch steps): Attention aperture wide open. Recommendation: `REUSE`.
  - 🟡 **AMBER** (`65%–80%` window fill OR `>=80` active-epoch steps while `<80%` fill): Context degradation beginning. Recommendation: `COMPACT_SOON`.
  - 🔴 **RED ALERT** (`>=80%` window fill): Context cliff active. Recommendation: `HANDOFF_OR_COMPACT`.

#### C. Zero-Exploration Invariant
All specialist subagent archetypes (`agyis_builder`, `agyis_reviewer`, `agyis_auditor`) enforce the **Zero-Exploration Invariant**:
- Blind recursive shell sweeps (`ls -R`, `find`, unbounded `rg`) and legacy sweep aliases (`list_dir`, `find_by_name`) are prohibited.
- Subagents open target files directly (`read_file`) from the plan or prompt instructions, or communicate back to the coordinator (`send_message` / `post_message`) and halt immediately.

#### D. Developer CLI Integration
- `agyis subagents [--json] [--brain-dir <path>]`: Renders formatted ASCII table of live active subagents.
- `agyis status`: Automatically embeds live active subagents health table when subagents are active.

---

### 3.6 The `psl-compaction-advisory` Contract (PreInvocation, ADR-033)

The compaction advisory hook operates at the `PreInvocation` event boundary, evaluating model token runway *before* prompts are submitted to the underlying LLM.

#### A. Registration in `hooks.json`
```json
{
  "psl-compaction-advisory": {
    "PreInvocation": [
      {
        "type": "command",
        "command": "python3 -m harness.hooks.runner pre-invocation",
        "timeout": 5
      }
    ]
  }
}
```

#### B. Architectural Behavior & Invariants (`harness.trajectory` SSOT)
1. **Dynamic Epoch & Runway Evaluation**:
   - Delegates read-only SQLite access (`file:<path>?mode=ro`, `DEFAULT_SQLITE_TIMEOUT = 0.5`s, clamped via `get_compaction_sqlite_timeout()`) and protobuf decoding to `read_db_trajectory_state()` (`harness/trajectory/`).
   - Evaluates active context ratio against `maxContextTokens` (`get_scaled_thresholds()`) and derives epoch-scoped step horizon (`epoch_steps` bounded by `CHECKPOINT_STEP_TYPE = 23` checkpoints; `SOFT_EPOCH_STEP_ADVISORY = 80` with `stepIdx` / `initialNumSteps` / `invocationNum` fallback).
   - Emits role-appropriate directives anchored via `ROLE_PERSONA_PROMPTS` (`ROLE_FLIGHT_DIRECTOR`, `ROLE_DEEP_EXECUTION`, `ROLE_FORENSIC_AUDITOR`, `ROLE_SWARM_ORCHESTRATOR`), bypassing native platform slash commands (`/compact`, `/plan`, `/boost`, etc.) and re-anchoring automatically upon post-compaction epoch transitions (`build_post_compaction_persona_prompt()`).
   - All directives—including role pinning, `80`-step epoch horizon nudges, and compaction alerts—are wrapped exclusively in the required nested `systemMessage` envelope (`{"systemMessage": {"systemMessage": "...", "metadata": {}}}`); deprecated `"ephemeralMessage"` is never emitted by `pre_invocation_hook.py`.
2. **De-Spammed Advisory Invariant**:
   - Tracked per-session inside `/tmp/agyis_harness_state_{uid}` (overridable via `AGYIS_HARNESS_STATE_DIR` / `PSL_HARNESS_STATE_DIR`).
   - When token consumption crosses the dynamically scaled `~90%` red threshold (`230,000` on `256k`; `460,000` on Gemini 4 `512k`; `900,000` on `1M`), injects a structured compaction directive into `injectSteps` **once** per epoch threshold crossing; subsequent turns emit a compact single-line badge to conserve prompt tokens.
3. **Carrier-Grade Pre-Compaction Checkpoint Awareness**:
   - Synchronizes with `agyis checkpoint generate` (`harness/delivery/compaction_checkpoint.py`), referencing `.agents/artifacts/checkpoints/<conv_id>.md`, `.agents/artifacts/cockpit_checkpoint.md`, and `.agents/artifacts/active_plan.md` for seamless state succession across turn compactions.
4. **Hermetic Fail-Open Protocol**:
   - On transcript lock contention or parse anomalies, the hook fails open with empty steps (`{"injectSteps": []}`), guaranteeing model prompt dispatch is never stalled.
