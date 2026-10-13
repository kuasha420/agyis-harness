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

## 3. Reference Implementation: `psl-agy-harness` Hooks

In `harness/hooks/`, we provide reference hooks:
1. `anti_loop_hook.py`: Intercepts repetitive consecutive calls to identical files/queries in `PreToolUse` and enforces the Strict Reactive Wait Invariant.
2. `output_compactor_hook.py`: PostToolUse deterministic 2KB output compactor preserving head, tail, and error lines (ADR-007, ADR-008).
3. `completion_fence_hook.py`: Validates test/verification state in `Stop` before allowing the agent to claim victory (ADR-022).
4. `command_safety_hook.py`: Audits `PreToolUse` shell execution, injects user toolchain PATH shims, enforces non-blocking network probe timeouts, and guarantees hermetic runtime safety (ADR-011, ADR-013, ADR-023).
5. `anti_drift_hook.py`: Intercepts file modifications in `PreToolUse` against declared implementation plan boundaries, enforces Native Plan-Mode Locks, and applies Auditor Write-Block Guards (ADR-024, ADR-025, ADR-031).

### 3.1 The `psl-stop-verification-fence` Contract (ADR-022)

The `psl-stop-verification-fence` hook enforces verification discipline by preventing agents from declaring completion when code has been modified without running tests.

#### A. Dual Event Registration in `hooks.json`
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
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 -m harness.hooks.runner verification-fence",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

#### B. Operational State Machine
1. **`PreToolUse` Interception**:
   - Matching tools: `write_to_file`, `replace_file_content`, `edit_file`.
   - If target file is recognized as code (`.py`, `.ts`, `.rs`, `.go`, etc.):
     - Sets `code_dirty = True`.
     - Appends target file to `last_modified_files`.
     - Resets `block_count = 0` (re-arming the fence if previously tripped).
   - Exemptions: Documentation (`.md`, `.txt`, `.rst`), assets (`.png`, `.svg`), lockfiles (`uv.lock`, `package-lock.json`), and git configs (`.gitignore`) do NOT dirty the state.
   - Always emits `{"decision": "allow"}` so the edit proceeds unhindered.

2. **`Stop` Event Evaluation**:
   - If `code_dirty == False`: Emits `{"decision": "allow"}`.
   - If `code_dirty == True`:
     - If `block_count < 2`: Increments `block_count` and emits:
       ```json
       {
         "decision": "continue",
         "reason": "Verification Required: Unverified code edits detected in: <files>. Execute 'python3 -m harness.cli test' or your project test suite before stopping."
       }
       ```
     - If `block_count >= 2`: Anti-deadlock safety valve trips! Emits:
       ```json
       {
         "decision": "allow",
         "warning": "Anti-deadlock valve tripped after 2 verification blocks. Exiting despite unverified edits."
       }
       ```

3. **Verification Clearance via Test Runner**:
   - Running `./psl test` or `python3 -m harness.cli test` executes the test suite.
   - Upon successful completion (`success == True`), clears `code_dirty = False`, resets `block_count = 0`, and sweeps all active session state files in `$PSL_HARNESS_STATE_DIR/verification_state_*.json`.


### 3.2 Command Safety & Subshell PATH Reliability Contract (ADR-023)

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
### 3.3 Plan-to-Execution Anti-Drift Verification Gate (ADR-024)

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

### 5. PreToolUse Auditor Write-Block Guard & Zero-Token Context Health Gauge (ADR-025)

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
- `psl subagents [--json] [--brain-dir <path>]`: Renders formatted ASCII table of live active subagents.
- `psl status`: Automatically embeds live active subagents health table when subagents are active.

