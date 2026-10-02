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
1. `anti_loop_hook.py`: Intercepts repetitive consecutive calls to identical files/queries in `PreToolUse`.
2. `output_truncator_hook.py`: Monitors tool output size in `PostToolUse` to prevent context explosion.
3. `completion_fence_hook.py`: Validates test/verification state in `Stop` before allowing the agent to claim victory.

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
            "command": "python3 -m harness.cli hook verification-fence",
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
            "command": "python3 -m harness.cli hook verification-fence",
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
