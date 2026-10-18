<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Official Lifecycle Hooks Specification (`hooks.json`)

## Overview
Antigravity lifecycle hooks allow execution of external shell commands or scripts at deterministic execution points in the agent loop. Hooks are defined in `hooks.json` at a customization root or inside an official plugin.

---

## 1. Event Types & Invocations

| Event | Execution Phase | Matcher Supported? | Payload Context | Expected Output |
| :--- | :--- | :--- | :--- | :--- |
| `PreToolUse` | Intercepts before tool execution | Yes (`matcher: "<regex>"`) | Tool name & arguments | Decision (`allow`, `deny`, `ask`, `force_ask`) + optional argument `overwrite` |
| `PostToolUse` | Runs immediately after tool execution | Yes (`matcher: "<regex>"`) | Step index & tool error (if any) | `{}` |
| `PreInvocation` | Runs before model prompt dispatch | No (flat list) | Invocation number, initial steps | `injectSteps` array (ephemeral messages or tool calls) |
| `PostInvocation` | Runs after model generates tool calls | No (flat list) | Model output summary | `injectSteps`, `terminationBehavior` (`force_continue`, `terminate`) |
| `Stop` | Intercepts agent loop termination | No (flat list) | Reason (`model_stop`, `error`, etc.), idle status | `decision` (`continue`, `stop`) + `reason` |

---

## 2. JSON I/O Contracts (camelCase Protojson)

### Common Payload Metadata (Sent on `stdin`)
```json
{
  "conversationId": "270b7abc-9b59-4f50-9c49-de3ed7e04f06",
  "workspacePaths": ["/workspace/psl-agy-harness"],
  "transcriptPath": "~/.gemini/antigravity/brain/.../transcript.jsonl",
  "artifactDirectoryPath": "~/.gemini/antigravity/brain/.../",
  "modelName": "auto"
}
```

### `PreToolUse` Decision Schema (Emitted on `stdout`)
```json
{
  "decision": "allow", // "allow" | "deny" | "ask" | "force_ask"
  "reason": "Detailed justification for the decision.",
  "overwrite": {
    "CommandLine": "normalized-command" // Shallow top-level argument override
  },
  "permissionOverrides": ["command(...)"]
}
```

### `Stop` Decision Schema (Emitted on `stdout`)
```json
{
  "decision": "continue", // "continue" blocks stop; any other value allows exit
  "reason": "Outstanding verification checks or unharvested background tasks."
}
```

---

## 3. Reference Implementation: `agyis-harness` Hooks

In `harness/hooks/`, we provide 6 deterministic hooks registered in `hooks.json`:
1. `command_safety_hook.py`: PreToolUse shell execution sanitizer, Python >= 3.12 uv runtime injector, and grep pattern probing exit normalizer (ADR-013).
2. `anti_loop_hook.py`: PreToolUse repetitive call breaker and Strict Reactive Wait enforcer.
3. `output_compactor_hook.py`: PostToolUse deterministic 2KB output compactor with DEF-04 pre-slice optimization for massive dumps.
4. `completion_fence_hook.py`: PreToolUse/PostToolUse/Stop verification fence with ADR-028 decoupled dirty state (`code_dirty` vs `spec_dirty`).
5. `token_proximity_guard.py`: PreToolUse context accumulation monitor decoding SQLite protobuf metadata and emitting ANSI threshold gauges.
6. `anti_drift_hook.py`: PreToolUse plan adherence guard and Auditor write-block enforcer.

### 3.1 The `psl-stop-verification-fence` Contract (ADR-022 / ADR-028)

The `psl-stop-verification-fence` hook enforces verification discipline by preventing agents from declaring completion when code or cleanroom specifications have been modified without formal verification.

#### A. Triple Event Registration in `hooks.json`
```json
{
  "psl-stop-verification-fence": {
    "PreToolUse": [
      {
        "matcher": "write_to_file|replace_file_content|edit_file",
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
        "matcher": "run_command|execute_command|bash|call_mcp_tool",
        "hooks": [
          {
            "type": "command",
            "command": "python3 -m harness.hooks.runner verification-fence",
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

5. **Formal Manifest Clearance (DEF-06)**:
   - Validates cleanroom clearance manifests in `.agents/ledger/manifest.json` against typed schemas (`status: "verified"`, 64-character lowercase SHA-256 `evidence_hash`, and non-empty `obligations` array where all entries have `status: "satisfied"`). If verified, clears `spec_dirty = False` automatically.

6. **Anti-Deadlock Safety Valve**:
   - If blocked twice consecutively (`block_count >= 2`), the safety valve trips and allows termination with warning, preventing infinite loops.

7. **Verification Clearance via Test Runner / Verify Command**:
   - Running `./agyis test` (or `python3 -m harness.cli test`) clears `code_dirty = False` and `spec_dirty = False`.
   - Running `agyis verify --spec` or `rea verify-reconstruction` clears `spec_dirty = False` without requiring test suite execution.

### 3.2 The `psl-token-proximity-guard` Contract (ADR-014 / ADR-028)

The token proximity guard monitors active session context accumulation to warn agents before they hit the catastrophic 50k token context cliff.

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

#### B. Decoding & Thresholds
1. **SQLite Sampling**: Directly queries `~/.gemini/antigravity/conversations/*.db` using read-only URI mode (`file:<path>?mode=ro`, timeout=1.0) to prevent database lock contention.
2. **Protobuf Extraction**: Reads the latest step from the `steps` table and decodes binary protobuf field 9 to extract exact prompt tokens (subfield 2) and cached content tokens (subfield 5).
3. **Compaction Checkpoint Detection**: Honors Antigravity compaction checkpoint barriers (enum 23 / 0x17), bounding token calculation to post-compaction steps.
4. **Threshold Indicators**:
   - `< 35,000 tokens`: Silent (nominal operation).
   - `35,000 - 44,999 tokens`: Emits an ANSI amber warning gauge to `stderr` advising approaching horizon limits.
   - `>= 45,000 tokens`: Emits a bold ANSI red alert and terminal bell (`\a`) warning that the 50k compaction threshold is imminent.
5. **Fail-Open Invariant**: Always outputs `{"decision": "allow"}` and exits 0. Tool calls are never interrupted.


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
- Enforces non-interactive pagers (`PAGER=cat` for `git`, `gh`).
- Injects certified CPython 3.12+ for inline Python scripts (`python3 -c`) and sanitizes f-string quote escapes.
- Surgical tail sanitization (`|| [ $? -eq 1 ]`) for standalone pattern searches (`grep`, `diff`).
### 3.4 Plan-to-Execution Anti-Drift Verification Gate (ADR-024)

The `anti_drift_hook.py` hook (`psl-anti-drift-guard`) intercepts file modifications in `PreToolUse` to ensure agents do not mutate files outside the boundaries of the approved implementation plan.

#### A. Registration in `hooks.json`
```json
{
  "psl-anti-drift-guard": {
    "PreToolUse": [
      {
        "matcher": "write_to_file|replace_file_content|edit_file",
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
   - Extracts targets from action headers (`#### [MODIFY] [file](...)`, `#### [NEW] path/to/file`, `#### [DELETE] ...`).
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
* **File Location**: `harness/hooks/anti_drift_hook.py`, `harness/subagents.py`

#### A. Auditor Permissions Paradox & Write-Block Guard
In the PSL Subagent Ladder protocol, the **Auditor** (`harness_auditor`) requires command execution privileges (`run_command`) to run automated tests and doctor diagnostics, but must never mutate source files or test fixtures. Because granting platform execute permissions often surfaces editing tools in the agent's environment, `check_auditor_write_block()` enforces a deterministic software fence in `PreToolUse`.

- **Interception Trigger**: Tool call is `write_to_file`, `replace_file_content`, or `edit_file`, AND calling agent role is `harness_auditor`, `auditor`, `qa_verifier`, or `PSL_SUBAGENT_ROLE=auditor`.
- **Response Contract**:
  ```json
  {
    "decision": "deny",
    "reason": "PSL Auditor Invariant: harness_auditor is strictly verification-only and cannot mutate files."
  }
  ```
- **Allowed Tools**: Read and command execution tools (`run_command`, `view_file`, `list_dir`, `grep_search`, `manage_task`) remain fully available for hermetic verification.

#### B. Zero-Token Context Estimator & Health Gauge
`estimate_subagent_context()` calculates subagent context consumption, step depth, and health status in microseconds with zero LLM API token overhead:
- **Transcripts $\le 2\text{ MB}$**: Exact line-by-line streaming parser extracting exact steps, characters, and explicit token telemetry in $<1.5\text{ ms}$.
- **Titan Transcripts $> 2\text{ MB}$**: Fast size-heuristic fallback estimating token volume and step depth in $<0.1\text{ ms}$ without loading titan payloads into RAM.
- **Threshold Health Zones**:
  - 🟢 **HEALTHY** ($<40\text{k tokens}$ AND $<40\text{ steps}$): Attention aperture wide open. Recommendation: `REUSE`.
  - 🟡 **AMBER** ($40\text{k}–80\text{k tokens}$ OR $40–80\text{ steps}$): Context degradation beginning. Recommendation: `COMPACT_RECREATE`.
  - 🔴 **RED ALERT** ($>80\text{k tokens}$ OR $>80\text{ steps}$): Context cliff active. Recommendation: `RETIRE`.

#### C. Zero-Exploration Invariant
All specialist subagent archetypes (`harness_builder`, `harness_reviewer`, `harness_auditor`) enforce the **Zero-Exploration Invariant**:
- Blind recursive exploration (`list_dir`, `find_by_name`) is prohibited.
- Subagents open target files directly from the plan or prompt instructions, or communicate back to the coordinator and halt immediately.

#### D. Developer CLI Integration
- `agyis subagents [--json] [--brain-dir <path>]`: Renders formatted ASCII table of live active subagents.
- `agyis status`: Automatically embeds live active subagents health table when subagents are active.

