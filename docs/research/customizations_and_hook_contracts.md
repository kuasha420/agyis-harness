<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Architectural Report: Google Antigravity Customization System, Hook Lifecycles & Runtime Contracts

## Executive Summary

The **Google Antigravity Customization System** provides an extensible, event-driven architecture that allows engineering teams to transform general-purpose autonomous agents into deterministic, codebase-aware specialist fleets. Through a declarative configuration hierarchy spanning **Workspace**, **Global**, and **Built-in** layers, the platform coordinates:
1. **Lifecycle Hooks (`hooks.json`)**: Synchronous command interceptors that gate tool execution (`PreToolUse`), sanitize tool outputs (`PostToolUse`), initialize sessions (`SessionStart`), inject dynamic guidance before model invocation (`PreInvocation`), inspect execution loop results (`PostInvocation`), and enforce verification gates before exit (`Stop`).
2. **Specialist Subagent Personas (`.agents/agents/*.md`)**: Declarative agent definitions governed by YAML frontmatter contracts specifying archetypes, role prompts, capability bundles, and strict tool permissions.
3. **Progressive Disclosure Skills (`SKILL.md`)**: On-demand procedural runbooks and executable utilities injected selectively to conserve context window budgets.
4. **Hierarchical Directory Rules (`AGENTS.md` / `GEMINI.md`)**: Upward-traversing behavioral constraints bound by strict byte-size caps and token budgets.
5. **Namespaced Plugins (`plugin.json`)**: Distributable bundles encapsulating skills, agents, rules, hooks, and MCP servers.

This report establishes the complete technical reference and ground-truth contract of the Antigravity customization engine, providing the formal architectural foundation for the PSL Agyis Harness specialist fleet.

---

## 1. Lifecycle Hook Architecture (`hooks.json`)

Lifecycle hooks execute external shell scripts or compiled binaries synchronously at deterministic transition points in the agent's core cognitive loop.

### 1.1 Configuration Schema and Placement

Hooks are declared in a single JSON object named `hooks.json`. Discovery evaluates hooks in:
- **Workspace Customization Root**: `.agents/hooks.json` (or `.agent/hooks.json`)
- **Plugin Bundles**: `<plugin_dir>/hooks.json`
- **Global User Configuration**: `~/.gemini/config/hooks.json`

```json
{
  "<hook-name>": {
    "enabled": true,
    "SessionStart": [ ... ],
    "PreToolUse": [ ... ],
    "PostToolUse": [ ... ],
    "PreInvocation": [ ... ],
    "PostInvocation": [ ... ],
    "Stop": [ ... ]
  }
}
```

*   **Top-Level Hook Keys**: Arbitrary unique strings (e.g. `"psl-anti-drift-guard"`, `"psl-stop-verification-fence"`).
*   **Sequential Merging**: When multiple named hook objects define handlers for the same event type (across plugins, workspace configs, or user settings), handlers are merged and executed sequentially in discovery order.
*   **Enablement Flag**: `"enabled": false` at the named hook level immediately disables all its handlers without deleting the configuration.

### 1.2 Event Topologies: Flat vs. Grouped Matcher

The six supported event types fall into two structural topologies:

| Event Type | Topology | Matcher Key | Purpose |
| :--- | :--- | :--- | :--- |
| `SessionStart` | **Flat** | N/A (Ignored) | Fires once when a conversation session is created. Injects startup context. |
| `PreToolUse` | **Grouped** | `matcher` (Regex) | Intercepts tool calls before execution. Gates, blocks, asks user, or overwrites tool arguments. |
| `PostToolUse` | **Grouped** | `matcher` (Regex) | Intercepts tool output after execution. Sanitizes, compacts, or logs execution results. |
| `PreInvocation` | **Flat** | N/A (Ignored) | Fires before the LLM is called. Injects transient or persistent steps into the prompt. |
| `PostInvocation` | **Flat** | N/A (Ignored) | Fires after tool calls finish for an invocation. Can force continuation or terminate. |
| `Stop` | **Flat** | N/A (Ignored) | Fires when the execution loop terminates. Functions as a completion fence. |

#### The Grouped Matcher Pattern (`PreToolUse`, `PostToolUse`)
For tool-specific events, handlers are wrapped inside matcher groups:
```json
"PreToolUse": [
  {
    "matcher": "write_to_file|replace_file_content",
    "hooks": [
      {
        "type": "command",
        "command": "python3 -m harness.hooks.runner anti-drift",
        "timeout": 5
      }
    ]
  }
]
```
- **Target Extraction**: Tool names are derived by lowercasing the internal step type and stripping the `CORTEX_STEP_TYPE_` prefix (e.g., `CORTEX_STEP_TYPE_RUN_COMMAND` -> `run_command`).
- **Regex Semantics**:
  - `"*"` or `""`: Matches all tools unconditionally.
  - `"run_command"`: Exact tool match.
  - `"run_command|view_file"`: Union match.
  - `"browser_.*"`: Prefix regular expression match.

### 1.3 Hook Handler Fields

Each individual handler object within a hook array supports:
- **`type`** *(string, optional)*: Defaults to `"command"`. Currently, `"command"` (shell execution) is the only supported runtime mechanism.
- **`command`** *(string, required)*: Shell command executed via `sh -c` on Unix/Linux, and `cmd /c` on Windows.
  - Tilde expansion (`~`) is performed automatically to the user's home directory.
  - **Working Directory Invariant**: The working directory (`cwd`) of the spawned hook process is explicitly set to the directory containing `hooks.json`.
- **`timeout`** *(int, optional)*: Process timeout in seconds. Defaults to `30`. In high-performance harnesses, timeouts are pinned between `2` and `5` seconds to prevent blocking UI threads.

---

## 2. Input/Output Payloads & Injection Schemas

All communication between the Antigravity engine and hook processes occurs over standard streams:
- **Ingress Context**: Passed as a JSON object on `stdin`.
- **Egress Response**: Emitted as a JSON object on `stdout`.
- **Encoding Standard**: All JSON keys strictly use **camelCase** protojson format (`conversationId`, `stepIdx`, `invocationNum`).

### 2.1 Common Input Fields (System Metadata)

Every hook payload passed on `stdin` includes common system metadata:

```json
{
  "conversationId": "<subagent-conversation-id>",
  "workspacePaths": ["<workspaceRoot>"],
  "transcriptPath": "<workspaceRoot>/.gemini/antigravity/transcript.jsonl",
  "artifactDirectoryPath": "<appDataDir>/brain/<subagent-id>",
  "modelName": "auto"
}
```

> [!NOTE]
> Directory naming in `transcriptPath` and `artifactDirectoryPath` reflects the hosting surface:
> - **Antigravity Desktop (Electron)**: `.gemini/antigravity/`
> - **Antigravity CLI (`agy`)**: `.gemini/antigravity-cli/`
> - **Antigravity IDE Extension**: `.gemini/antigravity-ide/`

---

### 2.2 Complete Hook Lifecycle Event Matrix

| Event | Engine Trigger Point | Ingress Payload (`stdin`) | Egress Control Contract (`stdout`) | Latency SLA |
| :--- | :--- | :--- | :--- | :--- |
| **`SessionStart`** | Once upon conversation creation | Common fields | `{"injectSteps": [...]}` | < 50ms |
| **`PreToolUse`** | Before tool step dispatch | Common fields + `toolCall: {name, args}`, `stepIdx` | `{"decision": "allow"\|"deny"\|"ask"\|"force_ask", "reason": "...", "overwrite": {...}, "permissionOverrides": [...]}` | < 10ms (SLA 5ms) |
| **`PostToolUse`** | Immediately after tool returns | Common fields + `toolCall: {name, args}`, `stepIdx`, `error` (if failed) | `{}` (Strict empty object) | < 10ms (SLA 5ms) |
| **`PreInvocation`** | Before LLM prompt compilation | Common fields + `invocationNum`, `initialNumSteps` | `{"injectSteps": [...]}` | < 5ms (SLA 2ms) |
| **`PostInvocation`** | After tool calls finish for an invocation | Common fields + `invocationNum`, `initialNumSteps` | `{"injectSteps": [...], "terminationBehavior": "force_continue"\|"terminate"\|""}` | < 10ms |
| **`Stop`** | When execution loop terminates | Common fields + `executionNum`, `terminationReason`, `error`, `fullyIdle` | `{"decision": "continue", "reason": "..."}` or `{"decision": "allow"}` | < 15ms |

---

### 2.3 `PreToolUse` Control Contract & Argument Rewriting

`PreToolUse` is the primary defensive gate of the agent platform.

```
       [LLM Emits ToolCall]
                 │
                 ▼
      ┌─────────────────────┐
      │ PreToolUse Hook     │
      └──────────┬──────────┘
                 │
      ┌──────────┴───────────────────────────┐
      ▼                  ▼                   ▼
["decision": "deny"]  ["decision": "ask"]  ["decision": "allow"]
  (Immediate Block)   ("force_ask" ignores    (Proceeds to Exec)
                       cached permission)            │
                                                     ▼
                                            ["overwrite": {...}]
                                            (Shallow argument merge)
                                                     │
                                                     ▼
                                           [Tool Executes with Mod Args]
                                           (Agent notified of rewrite)
```

#### Decision States
1. `"allow"`: Permits immediate tool execution without human interaction.
2. `"deny"`: Hard-blocks tool execution immediately. The agent receives a rejection message containing the `reason` string.
3. `"ask"`: Prompts the human operator for confirmation. Respects the operator's "Always Allow" cache.
4. `"force_ask"`: Prompts the human operator for confirmation, explicitly bypassing and ignoring cached "Always Allow" grants.

#### The `overwrite` Argument Rewrite Invariant
Hooks can mutate tool arguments dynamically prior to execution:
- **Shallow Merge**: The `overwrite` object is top-level merged into the tool's `args` dictionary. Keys present in `overwrite` replace existing keys wholesale; nested dictionaries are not deep-merged.
- **Agent Notification & Replay Integrity**: Because the model's replay trajectory records what the agent originally intended to call, whenever `overwrite` alters arguments, the tool result is prefixed with a platform notice:
  `[Notice: Hook rewrote tool arguments for keys: <key1>, <key2>]`.
  This guarantees that the model remains aware of runtime argument transformations (e.g. prepending hermetic PATH shims or appending non-interactive flags).

---

### 2.4 `PostToolUse` Contract & Output Compaction

- **Ingress Data**: Receives the original `toolCall`, the `stepIdx`, and an optional `error` string if the tool failed (e.g. non-zero exit code).
- **Strict Egress Schema**: The engine strictly expects an empty JSON object: `{}`. Emitting `{"decision": "allow"}` in `PostToolUse` is invalid protojson and triggers runner warnings.
- **Asynchronous Output Compaction Pattern**: While the hook must return `{}` on stdout, it can cache compacted outputs and compaction telemetry in `/tmp/agyis_harness_state/` or active SQLite session databases. This allows post-execution analyzers to audit large logs without overflowing the main context window.

---

### 2.5 The Step Injection Taxonomy (`injectSteps`)

Both `SessionStart`, `PreInvocation`, and `PostInvocation` can inject steps dynamically into the conversation via the `injectSteps` array. The platform supports three distinct step types with fundamentally different persistence and visibility semantics:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        injectSteps Schema                              │
└───────┬─────────────────────────┬───────────────────────────────┬──────┘
        │                         │                               │
        ▼                         ▼                               ▼
 1. ephemeralMessage       2. systemMessage                3. userMessage
 ┌──────────────────────┐  ┌─────────────────────────────┐ ┌──────────────┐
 │ plain string         │  │ nested object:              │ │ plain string │
 │ {"ephemeralMessage": │  │ {"systemMessage": {         │ │ {"userMessage│
 │    "..."}            │  │    "systemMessage": "...",  │ │    ": "..."} │
 │                      │  │    "metadata": {...}}}      │ │              │
 ├──────────────────────┤  ├─────────────────────────────┤ ├──────────────┤
 │ Scope: Transient     │  │ Scope: Persistent           │ │ Scope: User  │
 │ (dropped after turn) │  │ (persisted in SQLite/JSONL) │ │ (chat turn)  │
 └──────────────────────┘  └─────────────────────────────┘ └──────────────┘
```

#### Step Type Comparison Matrix

| Step Type | Structure | Persistence Lifecycle | Visibility to Model | Best Use Case |
| :--- | :--- | :--- | :--- | :--- |
| **`ephemeralMessage`** | Plain String | **Transient**: Survives for the immediate invocation turn only. Dropped before trajectory serialization. | Injected into active context window directly before model sampling. | Imminent compaction warnings (Issue #83), real-time token proximity warnings, dynamic linter hints. |
| **`systemMessage`** | Nested Object: `{"systemMessage": {"systemMessage": "...", "metadata": {...}}}` | **Persistent**: Written permanently to SQLite `steps` table and `transcript.jsonl`. Survives compaction. | Inlined into system instructions across all subsequent turns. | Session onboarding notices, project role declarations, environmental constraints, compliance policies. |
| **`userMessage`** | Plain String | **Persistent**: Treated as a synthetic user turn. | Visible as a standard user prompt in conversation history. | Autonomous continuation prompts, automated test suite resumption, subagent handoff triggers. |

> [!CAUTION]
> **Syntax Trap**: Declaring `{"systemMessage": "my message"}` fails protojson decoding. `systemMessage` **requires a nested dictionary** with an inner `systemMessage` key:
> `{"systemMessage": {"systemMessage": "text content", "metadata": {}}}`.
> Conversely, `ephemeralMessage` and `userMessage` accept direct plain strings.

---

### 2.6 `Stop` Completion Fence Mechanics

When the agent's execution loop determines it should stop, it triggers the `Stop` lifecycle event.

#### Ingress Fields:
- **`executionNum`** *(int)*: Current loop execution index.
- **`fullyIdle`** *(bool)*: `true` if all spawned background tasks (`manage_task`) have finished execution.
- **`error`** *(string)*: Populated if stopping due to an uncaught runtime error.
- **`terminationReason`** *(string)*: Stripped `ExecutorTerminationReason` enum name:

| `terminationReason` | Trigger Scenario |
| :--- | :--- |
| **`NO_TOOL_CALL`** | Model concluded its thought process without emitting any tool calls (nominal stop). |
| **`MAX_INVOCATIONS`** | Execution reached the configured maximum turn/invocation threshold. |
| **`MAX_FORCED_INVOCATIONS`** | Model exceeded the upper ceiling for `force_continue` directives. |
| **`MAX_TOKEN_BUDGET_EXCEEDED`** | Context exceeded the session token budget. |
| **`ERROR`** | Unhandled platform or tool dispatcher exception. |
| **`USER_CANCELED`** | Human operator aborted execution via UI or `Ctrl+C`. |
| **`TERMINAL_STEP_TYPE`** | Stopped upon encountering a designated terminal step. |
| **`TERMINAL_CUSTOM_HOOK`** | Terminated by a custom `PostInvocation` hook returning `"terminate"`. |
| **`INJECTED_RESPONSE`** | Terminated following an external injected response. |

#### Egress Control & Continuation:
To prevent the agent from exiting prematurely before verifying its work:
```json
{
  "decision": "continue",
  "reason": "Verification Required: Unverified code edits detected in: [auth.py]. Execute 'agyis test' before stopping."
}
```
- **Loop Re-Entry**: Setting `"decision": "continue"` blocks termination and forces the engine to re-enter the execution loop.
- **Reason Prompting**: The `reason` string is automatically injected into the agent's context as a system instruction, directing it to rectify the condition.
- **Anti-Deadlock Safety Valve**: To prevent infinite loops when an agent cannot resolve verification failures, the PSL Completion Fence maintains a state counter: after **2 consecutive blocks**, the valve trips and returns `"decision": "allow"` with an explanatory warning.

---

## 3. Subagent & Custom Agent Frontmatter Contracts

Antigravity supports specialized custom subagents declared as Markdown files with YAML frontmatter.

### 3.1 Custom Agent Locations & Discovery

Custom agent specifications are resolved across three tiers:
1. **Workspace Project**: `.agents/agents/<name>.md` (shared with repository via git).
2. **Product Toolchain**: `harness/agents/<name>.md` (packaged harness templates).
3. **Global Machine**: `~/.gemini/config/agents/<name>.md` (user-wide personas).
4. **Plugin Bundles**: `plugins/<plugin_name>/agents/<name>.md`.

Subagents are invoked in chat via `@<agent_name>`, through the slash menu (`/`), or programmatically via the `invoke_subagent` tool.

---

### 3.2 Canonical Frontmatter Specification

```markdown
---
name: harness_auditor
archetype: auditor
description: Hermetic verification, doctor audit, sub-second test suite benchmarking, and Victory Auditor certification.
role: QA Verifier (Hermetic Benchmark & Victory Auditor)
subagent: true
mainAgent: false
inheritCustomizations: true
model: inherit
permissions:
  read: true
  write: false
  execute: true
  subagents: false
  mcp: false
  enable_write_tools: false
tools:
  - view_file
  - list_dir
  - grep_search
  - find_by_name
  - run_command
  - manage_task
  - schedule
  - send_message
allowed_tools:
  - view_file
  - list_dir
  - grep_search
  - find_by_name
  - run_command
  - manage_task
  - schedule
  - send_message
---
```

#### Field Specifications:

| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| **`name`** | string | Required | Unique identifier (lowercase alphanumeric, underscores/hyphens). Used for `@<name>` dispatch and `invoke_subagent`. |
| **`archetype`** | string | `"executioner"` | Behavioral profile: `executioner`, `hammer`, `auditor`, `planner`, `coordinator`, `main`, `custodian`. |
| **`description`** | string | Required | Functional description evaluated by the model router to select subagents. |
| **`role`** | string | Archetype | Human-readable persona title. |
| **`subagent`** | boolean | `true` | Declares whether this persona can be invoked as a subagent. |
| **`mainAgent`** | boolean | `true` | Allows persona to serve as the root conversation agent. |
| **`inheritCustomizations`** | boolean | `true` | Propagates workspace rules (`AGENTS.md`), parent plugins, and global configurations down into the subagent context. |
| **`model`** (or `modelTier`) | string | `"inherit"` | Model selection: `"inherit"` (inherits parent model), `"pro"`, `"flash"`, `"flash_lite"`. |
| **`permissions`** | object | Defaults | Tool group permission flags (`read`, `write`, `execute`, `subagents`, `mcp`, `enable_write_tools`). |
| **`tools`** / **`allowed_tools`** | string[] | Required | Explicit list of active platform tools. |
| **`skills`** | string[] | `[]` | Optional list of bundled skill identifiers made immediately available. |

---

### 3.3 The Antigravity Platform Hanging Bug & Safe Tool Gating

#### The Platform Hanging Bug Root Cause
In Antigravity's subagent dispatcher, declaring tool names in `tools:` or `allowed_tools:` that are **unrecognized by the platform executor** causes the subagent process to hang indefinitely without throwing an exception or returning an error message.
- **Common Triggers**:
  - Deprecated or speculative tool names (e.g. `edit_file`, `bash`, `execute_command`, `str_replace_editor`).
  - Statically declaring MCP tools (`call_mcp_tool`, `list_resources`, `read_resource`) in the frontmatter `tools:` array.

#### The Safe MCP Tool Integration Pattern
MCP tools **must not** be listed statically in `tools:` or `allowed_tools:`. Instead, MCP tools are dynamically exposed to subagents by setting:
```yaml
permissions:
  mcp: true
inheritCustomizations: true
```
The language server dynamically binds available MCP servers and tools without polluting the static platform tool registry.

#### The 20 Platform Tools (`ANTIGRAVITY_PLATFORM_TOOLS`)
Only the following 20 tools may be safely declared in agent frontmatter:
```text
view_file, list_dir, grep_search, find_by_name,
write_to_file, replace_file_content,
run_command, manage_task,
invoke_subagent, send_message, manage_subagents, define_subagent,
schedule, generate_image,
read_url_content, search_web, ask_question
```

---

### 3.4 Pre-Verified Capability Bundles Matrix

To guarantee mathematical consistency between declared permissions and tool availability, the harness defines six standardized capability bundles:

| Capability Bundle | Allowed Tools | Permissions Object | Target Specialist Roles |
| :--- | :--- | :--- | :--- |
| **`read_only`** | `view_file`, `list_dir`, `grep_search`, `find_by_name`, `read_url_content`, `search_web`, `send_message` | `read: true`, `write: false`, `execute: false`, `subagents: false` | `harness_reviewer` (Hammer), Code Reviewer, Security Inspector |
| **`verifier`** | `read_only` + `run_command`, `manage_task` | `read: true`, `write: false`, `execute: true`, `subagents: false` | `harness_auditor` (Auditor), `harness_custodian` (Custodian), QA Benchmark Verifier |
| **`adversarial_verifier`** | `verifier` + `write_to_file`, `replace_file_content` | `read: true`, `write: true`, `execute: true`, `subagents: false` | Stress Test Generator, Fuzzing Oracle, Mutation Verifier |
| **`builder`** | `verifier` + `write_to_file`, `replace_file_content` | `read: true`, `write: true`, `execute: true`, `subagents: false` | `harness_builder` (Executioner), Core Implementer |
| **`orchestrator`** | `read_only` + `invoke_subagent`, `send_message`, `manage_subagents`, `manage_task`, `ask_question` | `read: true`, `write: false`, `execute: false`, `subagents: true` | `coordinator`, Swarm Lead, Milestone Flight Director |
| **`full`** | All 20 platform tools | `read: true`, `write: true`, `execute: true`, `subagents: true`, `mcp: true`, `enable_write_tools: true` | `agyis_architect` (Lead Architect / Main Persona) |

#### Deterministic Multi-Layer Gating:
1. **Frontmatter Permission Scoping**: Agents declared with `subagents: false` cannot call `invoke_subagent`, preventing dangerous subagent recursion bombs. Agents with `write: false` have file modification tools stripped from their prompt.
2. **Static Validation Gate (`agyis agents validate`)**: Verifies that `permissions` and `tools` do not contradict (e.g. flagging an error if `write_to_file` is listed when `write: false`).
3. **Runtime PreToolUse Interception (`anti_drift_hook.py`)**: `check_auditor_write_block()` intercepts tool calls at runtime. If an LLM hallucinates a `write_to_file` call while executing under a read-only role (`auditor`, `hammer`, `planner`, `coordinator`), the hook hard-blocks the execution with `"decision": "deny"`.

---

## 4. Loading Priority, Precedence & Conflict Resolution

Antigravity employs a 5-tier discovery hierarchy to merge configurations across local workspaces, team distributions, and global user profiles.

```
┌─────────────────────────────────────────────────────────────┐
│ Tier 1: Workspace Project (CWD up to Repository Root)       │  ▲ Highest Priority
├─────────────────────────────────────────────────────────────┤  │ (Overrides all below)
│ Tier 2: Workspace Declared Configs (skills.json/plugins.json)│  │
├─────────────────────────────────────────────────────────────┤  │
│ Tier 3: Global User Discovery (~/.gemini/config/)           │  │
├─────────────────────────────────────────────────────────────┤  │
│ Tier 4: Built-in Customizations (/builtin/skills/, plugins) │  │
├─────────────────────────────────────────────────────────────┤  │
│ Tier 5: Global Declared Configs (~/.gemini/config/*.json)   │  ▼ Lowest Priority
└─────────────────────────────────────────────────────────────┘
```

### 4.1 Discovery Traversal Mechanics

1. **Upward Workspace Crawl**: When a session initializes or a file is accessed, the language server crawls upward from the current working directory to the nearest repository root (identified by `.git`).
2. **Recognized Customization Roots**:
   - `.agents/` (Canonical modern standard)
   - `.agent/`, `_agents/`, `_agent/` (Supported legacy fallbacks, auto-harmonized by `agyis harmonize`)
3. **Path Resolution Rules**:
   - Absolute paths: `/path/to/customization`
   - Home-relative paths: `~/my-skills`
   - Workspace-relative paths: `tools/skills` (resolves relative to the directory containing the config, falling back to repository root).

---

### 4.2 Component Merging and Conflict Resolution

#### Skills (`SKILL.md`)
- **Naming Key**: The `name` frontmatter string is the unique key across the entire session.
- **Collision Rule**: If two skills share identical names, the higher-priority tier wins. Workspace-local skills override global skills, which override built-in skills.
- **Progressive Disclosure**: Skills are never inlined into prompt context by default. Only their `name` and `description` are exposed in system prompts. Full instructions and scripts are read only when activated.

#### Rules (`AGENTS.md` / `GEMINI.md`)
- **Discovery**: Crawls upward from file directory to repository root.
- **Deduplication**: Deduplicated strictly by resolved **absolute file path**. A rule file is never injected more than once in a single turn.
- **Context Budget Constraints**:
  - **Per-File Cap**: Strictly capped at **24,000 bytes** (24KB). Content exceeding 24KB is truncated at the nearest line boundary.
  - **Aggregate Token Budget**: Always-on and global rules share a dedicated **20,000 token budget** (`defaultRulesBudget`), completely isolated from skills and MCP budgets.
  - **Budget Demotion**: When aggregate rules exceed 20,000 tokens, lower-priority rules are demoted from full inlined text to file path pointers, allowing the model to inspect them on-demand via `view_file`.
  - **Builtin Exemption**: Rules shipped by built-in plugins are exempt from the 20,000 token budget and are always inlined in full.

#### Lifecycle Hooks (`hooks.json`)
- **Collision Rule**: Named hook keys (e.g. `psl-anti-drift-guard`) are merged across all discovered files.
- **Execution Order**: Multiple handlers matching the same event are executed sequentially in discovery order.
- **Hard Disabling**: Setting `"enabled": false` at the named hook level immediately disables all handlers under that key.

#### Plugins (`plugin.json`)
- **Identity Identifier**: A plugin's true operational identity is its **install directory name** (`dir`), NOT the `name` field in `plugin.json`.
- **Enablement State**: Whether a plugin is active is stored in `~/.gemini/config/config.json` under `plugins.<dir>.enabled`.
- **Override Invariant**: Settings in `config.json` **always override** the `"disabled": true` declaration in `plugin.json`. This ensures that user enablement choices survive plugin upgrades and re-installations.

#### MCP Servers (`mcp_config.json`)
- **Transports**: Supports **Stdio** (local executable spawned by language server) and **Streamable HTTP** (remote HTTP endpoints). Legacy SSE is deprecated.
- **Collision Rule**: Server names share a single global namespace. A plugin registering `"sqlite"` collides with a user-level `"sqlite"`. Plugins must prefix their MCP servers with the plugin directory name (e.g. `"team-tools-sqlite"`).

---

## 5. Best-Practice Patterns for Harness Enforcement

The PSL Agyis Harness codifies three core architectural decisions to govern hook implementations:

### 5.1 Zero Third-Party Dependencies (ADR-014)
Harness lifecycle hooks run directly in the host execution loop before tools or models fire.
- All hook modules (`harness/hooks/*.py`) must strictly depend on **CPython 3.12+ standard library modules** (`json`, `sys`, `os`, `re`, `pathlib`, `sqlite3`, `io`, `time`).
- Hooks must never import external packages (`pydantic`, `requests`, `pytest`) that could fail due to virtualenv isolation or missing site-packages.

### 5.2 Sub-Second Benchmark Invariant (ADR-015)
Because hooks run synchronously and block the agent's cognitive loop, hook latency directly degrades agent throughput.
- **Hook Execution SLA**: Individual hooks must complete execution in **sub-milliseconds** (<5.0ms maximum allowable; typical harness execution is **0.1ms to 0.75ms**).
- **SQLite Optimization**: State databases are opened with read-only URI mode (`file:{path}?mode=ro&uri=true`) and aggressive timeouts (`timeout=0.5`).
- **Pre-slicing Optimization**: When inspecting large command outputs in `PostToolUse`, middle text exceeding 200,000 characters is pre-sliced into 100KB head/tail blocks before invoking `splitlines()`, avoiding memory spikes and regex catastrophic backtracking.

### 5.3 Fail-Open Resilience & Anti-Deadlock Guarantee (AC8)
A crashed or hanging lifecycle hook can permanently freeze the Antigravity user interface.
- **The Standalone Runner (`harness.hooks.runner`)**: All hook invocations route through a fail-safe dispatcher that catches all exceptions (`SyntaxError`, `ImportError`, `RuntimeError`).
- **Fail-Open Egress**:
  - `PreToolUse` / `Stop` fallback: emits `{"decision": "allow"}`.
  - `PostToolUse` fallback: emits `{}`.
  - `PreInvocation` fallback: emits `{"injectSteps": []}`.
- **Diagnostic Logging**: Traces are piped strictly to `sys.stderr`, leaving `sys.stdout` clean for protojson parsing.
- **Exit Code 0**: Hook processes must always exit with return code `0` to prevent the platform shell executor from treating the tool invocation as aborted.

### 5.4 Single-Source Skill Deduplication
- Duplicating global plugin skills inside workspace `.agents/skills/` bleeds approximately **4,500 tokens/turn** of redundant context into every prompt.
- The harness enforces single-source hygiene via `agyis skills --prune-duplicates`, respecting the 3-tier boundary: Project Specialist > User Environment > Global Plugin.

---

## 6. Implementation Summary for Fleet Architecture

To scaffold the specialist fleet for the PSL Agyis Harness, the following configuration topology is established:

```text
psl-agy-harness/
├── .agents/
│   ├── hooks.json                # Registers PreToolUse, PostToolUse, PreInvocation, Stop
│   ├── agents/                   # Active specialist subagents (auditor, builder, reviewer)
│   │   ├── agyis_architect.md    # Main Lead Architect (full bundle)
│   │   ├── harness_auditor.md    # QA Verifier (verifier bundle, write: false)
│   │   ├── harness_builder.md    # Executioner (builder bundle, write: true)
│   │   ├── harness_custodian.md  # Git Commit Gate (verifier bundle, write: false)
│   │   ├── harness_reviewer.md   # Hammer (read_only bundle, write: false)
│   │   ├── planner.md            # Solution Architect (planner bundle, exec: false)
│   │   └── coordinator.md        # Swarm Lead (orchestrator bundle, exec: false)
│   └── rules/
│       └── AGENTS.md             # Consolidated project rules (<24KB, <20k tokens)
└── harness/
    ├── hooks/                    # Pure Python 3.12 standard-library hook modules
    │   ├── runner.py             # Fail-open dispatcher (<2ms)
    │   ├── command_safety_hook.py# PreToolUse command sanitizer & argument rewriter
    │   ├── anti_drift_hook.py    # PreToolUse plan boundary & role write blocker
    │   ├── anti_loop_hook.py     # PreToolUse redundant call breaker
    │   ├── output_compactor_hook.py # PostToolUse 2KB smart compactor
    │   ├── pre_invocation_hook.py   # PreInvocation role-tailored compaction advisory
    │   ├── completion_fence_hook.py # Stop event test verification fence
    │   └── token_proximity_guard.py # PreToolUse token threshold monitor
    └── subagents/                # Spec loader, archetype models, validation gate
```

By adhering strictly to the protojson schemas, fail-open invariants, and safe toolgroup capability bundles cataloged in this report, the specialist fleet operates with deterministic reliability, sub-second verification latency, and zero platform freeze risks.
