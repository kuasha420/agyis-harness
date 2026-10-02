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
  "workspacePaths": ["/home/kuasha/Dev/psl-agy-harness"],
  "transcriptPath": "/home/kuasha/.gemini/antigravity/brain/.../transcript.jsonl",
  "artifactDirectoryPath": "/home/kuasha/.gemini/antigravity/brain/.../",
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
