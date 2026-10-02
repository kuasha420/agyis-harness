# Antigravity Platform Surface Mapping: Deconstruction & Empirical Gap Analysis

**Document**: Canonical Architecture & Surface Mapping Specification  
**Project**: PSL Harness for Google Antigravity™ (`psl-agy-harness`)  
**Publisher**: Purrfect Software Limited (PSL)  
**License**: Apache-2.0  
**Status**: Canonical Reference & Operational Guide  
**Empirical Baseline**: Mined from 348 Workstation Sessions (140,005 Trajectory Steps, 64,065 Tool Calls, 2,232 Tool Failures, 5,773 Tool Loops)

---

## Executive Summary

Google Antigravity provides an extensible multi-tier agent execution runtime. However, developer tooling and custom harnesses frequently fail due to architectural mismatches: applying procedural prompt instructions where deterministic lifecycle hooks are required, polling asynchronous primitives that already feature reactive event wakeups, or overwhelming model context windows when native tool filtering and token compaction controls exist out of the box.

This specification provides the definitive deconstruction of all official Antigravity developer surfaces:
1. **The Antigravity CLI (`agy`)**: Interactive TUI, non-interactive batch/print execution, and structured streaming via NDJSON (`stream-json`).
2. **The Antigravity 2.0 Desktop Platform**: Electron-based orchestrator, HTML auxiliary generative UI, background task supervision, terminal multiplexer, and reactive scheduling.
3. **The Official Python SDK (`google-antigravity`)**: The three-pillar architecture (`Agent`, `Conversation`, `Connection`), capability configurations, fine-grained safety policies, and session leasing.
4. **The Lifecycle Hooks Engine (`hooks.json` & SDK Hooks)**: Deterministic pre/post-tool and pre/post-invocation event interception, payload contracts, shallow argument `overwrite`, and trajectory completion gating (`Stop`).
5. **Model Context Protocol (MCP) Boundaries**: Stdio vs. Streamable HTTP/SSE transports, tool filtering allowlists/denylists, and policy binding.

Following the platform deconstruction, this document conducts an exhaustive **Empirical Gap Analysis** matching each platform capability against the real-world failure distributions cataloged in our workstation telemetry audit report (`docs/taxonomy/workstation-audit-report.md`).

---

## 1. Platform Topology: The Multi-Tier Extension Model

```
+----------------------------------------------------------------------------------------------------+
|                                    Antigravity Platform Runtime                                    |
|                                                                                                    |
|  +-----------------------------+  +-------------------------------+  +--------------------------+  |
|  |     Antigravity CLI (agy)   |  |   Antigravity 2.0 Desktop     |  |   Official Python SDK    |  |
|  |                             |  |   (Electron / IDE Host)       |  |  (google-antigravity)    |  |
|  |  * Interactive TUI          |  |  * Chat Canvas & Mentions     |  |  * Agent Context Manager |  |
|  |  * Batch Print (-p)         |  |  * HTML Aux Pane (GenUI)      |  |  * Conversation State    |  |
|  |  * Stream NDJSON Protocol   |  |  * Reactive Background Tasks  |  |  * Strategy Transports   |  |
|  |  * Subcommands (mcp, plugin)|  |  * Terminal Multiplexer (TUI) |  |  * Declarative Policies   |  |
|  +--------------+--------------+  +---------------+---------------+  +------------+-------------+  |
+-----------------|---------------------------------|-------------------------------|----------------+
                  |                                 |                               |
                  +---------------------------------+-------------------------------+
                                                    |
                                                    v
+----------------------------------------------------------------------------------------------------+
|                               Core Language Server & Agent Execution Loop                          |
|                                                                                                    |
|  [PreInvocation Hook] -> [Model Inference (Gemini)] -> [PostInvocation Hook]                      |
|                                         |                                                          |
|                                         v (Tool Call Generated)                                    |
|  [PreToolUse Hook]    -> [Safety Policy Evaluation] -> [Tool Dispatch] -> [PostToolUse Hook]       |
|  (Gate / Arg Overwrite)  (9-Level Ladder Check)       (Built-in / MCP)    (Audit / Truncation)     |
|                                                                                                    |
|  [Trajectory Idle]    -> [Stop Hook Gating] (Continue vs Allow Stop)                               |
+---------------------------------------------------+------------------------------------------------+
                                                    |
         +------------------------------------------+----------------------------------------+
         |                                          |                                        |
         v                                          v                                        v
+-----------------------+              +--------------------------+             +--------------------+
|  Built-in Tools       |              |  Model Context Protocol  |             |  Custom Extensions |
|  * run_command        |              |  (FastMCP / JSON-RPC)    |             |  * Skills / Rules  |
|  * view_file          |              |  * Stdio Subprocess      |             |  * Custom Prompts  |
|  * replace_file_content              |  * Streamable HTTP / SSE |             |  * Subagent Trees  |
|  * manage_task        |              |  * Tool Filtering Filter |             |  * Sidecar Daemons |
+-----------------------+              +--------------------------+             +--------------------+
```

---

## 2. Surface Deconstruction: Antigravity CLI (`agy`)

The Antigravity CLI binary (`/usr/bin/agy`) serves as the primary headless and terminal-native developer surface. It executes the full agent engine locally without requiring an Electron graphical display.

### 2.1 Invocation Modes

| Mode | Command Invariant | Intended Environment | Characteristics |
| :--- | :--- | :--- | :--- |
| **Interactive TUI** | `agy` | Developer Terminal | Full screen raw terminal UI, rich markdown rendering, interactive approvals, slash command menu, dynamic prompt editing. |
| **Session Resumption** | `agy --continue`<br>`agy -c`<br>`agy --conversation <ID>` | Reconnect / Recovery | Resumes the most recent conversation or attaches directly to a specific UUID session in `~/.gemini/antigravity-cli/`. |
| **Interactive Launch** | `agy -i "<prompt>"`<br>`agy --prompt-interactive "<prompt>"` | Guided Sessions | Seeds the initial prompt and immediately transitions into the interactive TUI. |
| **Non-Interactive Batch** | `agy --print "<prompt>"`<br>`agy -p "<prompt>"` | Scripts, Cron, Headless | Executes single-shot prompts, runs until fully idle or stop condition, prints model output to stdout, and exits. |
| **Stream NDJSON** | `agy --input-format stream-json --output-format stream-json` | Daemon Harnesses, CI/CD | Headless bidirectional IPC over standard I/O; consumes NDJSON messages line-by-line and streams back structured lifecycle events. |

### 2.2 Print & Batch Flags (`--print`)
When running batch automation via `agy -p`, the following flags govern agent behavior:
- `--effort <low|medium|high>`: Configures Gemini extended thinking / reasoning budget. `high` allocates maximum token depth for architectural synthesis; `low` prioritizes execution speed.
- `--dangerously-skip-permissions`: Auto-approves all tool execution requests (`run_command`, file modifications) without pausing for human interactive prompts. Essential for non-interactive test runners and CI/CD harnesses.
- `--print-timeout <duration>`: Hard timeout ceiling for print mode execution (default: `5m0s`). Prevents unconstrained agent execution loops.
- `--mode <accept-edits|plan>`: Sets execution profile. `accept-edits` immediately applies file modifications; `plan` forces the agent into planning mode before performing mutations.
- `--sandbox`: Runs shell execution inside an OS-level restricted sandbox (namespaces/cgroups/seatbelt depending on platform).
- `--disable-slash-commands`: Disables interactive slash command and skill auto-expansion during print processing.
- `--json-schema <path|string>`: Enforces strict structured output schema validation on the final trajectory result.
- `--add-dir <path>`: Extends workspace context to multiple repository roots (repeatable flag).
- `--log-file <path>`: Directs raw CLI engine and trace logs to a designated filesystem destination.

### 2.3 The Structured Streaming Protocol (`stream-json`)
For programmatic harnesses (including `psl-agy-harness` test runners), `stream-json` provides an NDJSON-based interface:
```bash
# Bi-directional stream invocation
agy --input-format stream-json --output-format stream-json --dangerously-skip-permissions
```
- **Input Stream (`stdin`)**: Accepts newline-delimited JSON objects containing turn prompts or steering injections:
  ```json
  {"prompt": "Run test suite and fix failures", "effort": "high"}
  ```
- **Output Stream (`stdout`)**: Emits fine-grained execution events in real time:
  - `turn_start`: Marks trajectory initialization.
  - `thought_delta`: Emits incremental reasoning tokens.
  - `tool_call`: Emits tool name and arguments before execution.
  - `tool_result`: Emits tool status and output summary.
  - `message_delta`: Emits visible candidate response tokens.
  - `turn_complete`: Emits final token usage, execution stats, and trajectory status.

### 2.4 Subcommand Reference

```bash
agy <subcommand> [flags] [args]
```

- **`agy plugin`**: Manage plugin packages:
  - `list`: List all imported, installed, and discovered plugins.
  - `import [source]`: Ingest plugins from external ecosystems (`gemini` or `claude`).
  - `install <target>`: Install plugin packages (supports `plugin@marketplace`).
  - `uninstall <name>`: Remove an installed plugin.
  - `enable <name>` / `disable <name>`: Toggle active state of installed plugins.
  - `validate [path]`: Validate manifest schema (`plugin.json`) and directory layout.
  - `link <mp> <target>`: Create marketplace symlinks.
- **`agy mcp`**: Manage Model Context Protocol server registrations:
  - `add [flags] <name> <commandOrUrl> [args...]`: Register stdio or HTTP/SSE MCP server.
    - Flags: `-e`, `--env KEY=value` (repeatable); `-H`, `--header "Key: Value"` (repeatable); `-t`, `--type stdio|http`.
  - `remove <name>`: Unregister an MCP server.
  - `list`: Display configured MCP servers and operational status.
  - `enable <name>` / `disable <name>`: Toggle server visibility without removing configuration.
- **`agy agent` / `agy agents`**: Enumerate available agent personas and configurations.
- **`agy models`**: Query Gemini model targets available to the current credentials.
- **`agy remote-control`**: Control the background daemon enabling out-of-band workstation orchestration:
  - `start`: Register and launch background daemon.
  - `status`: Query daemon connectivity and active sessions.
  - `stop`: Terminate the daemon process.
- **`agy mic-serve`**: Stream local workstation microphone audio to a remote CLI session.
- **`agy install`**: Bootstrap shell environment paths, autocompletions, and environment variables.

---

## 3. Surface Deconstruction: Antigravity 2.0 Desktop Platform

Antigravity 2.0 is an Electron-based workstation environment that hosts the Language Server runtime, orchestrating agent execution across multiple rich visual and asynchronous surfaces.

```
+----------------------------------------------------------------------------------------------------+
|                                    Antigravity 2.0 Desktop UI                                      |
|                                                                                                    |
|  +--------------------+  +-------------------------------------+  +-----------------------------+  |
|  | Left-Hand Sidebar  |  | Main Chat Canvas                    |  | Auxiliary Workspace Pane    |  |
|  |                    |  |                                     |  |                             |  |
|  | * Projects Root    |  | * Slash Commands (/goal, /schedule) |  | [HTML Generative UI / Tab]  |  |
|  | * Active Sessions  |  | * @ Mentions (@file, @terminal)     |  | * Rich D3 / SVG Metrics     |  |
|  | * Scheduled Tasks  |  | * Visual Diff Review                |  | * Interactive Forms         |  |
|  | * Skills / Rules   |  | * Multi-turn Steer / Fences         |  | * UI Component Sandbox     |  |
|  | * Settings Manager |  |                                     |  |                             |  |
|  |                    |  |                                     |  | [Background Tasks Pane]     |  |
|  |                    |  |                                     |  | * Daemon Task Watcher       |  |
|  |                    |  |                                     |  | * Reactive Notification Bus |  |
|  +--------------------+  +-------------------------------------+  +-----------------------------+  |
+----------------------------------------------------------------------------------------------------+
```

### 3.1 Auxiliary Generative UI (HTML Pane)
Antigravity 2.0 integrates an internal browser viewport capable of rendering rich, interactive generative HTML artifacts. Agents produce HTML widgets via markdown code blocks or dedicated files:
- **Rendering Model**: Isolated iframe sandbox supporting modern web standards (SVG, Canvas, CSS animations, JavaScript).
- **Use Cases**: Live metric cockpits, topology graphs, hardware cluster visualizers, interactive approval forms, and component mockups.
- **Contract**: Communication back to the agent is bridged via structured DOM events or clipboard transfers.

### 3.2 Background Task Supervision & The Reactive Wakeup Invariant
The desktop runtime provides an asynchronous execution engine managed via the built-in `manage_task` and `schedule` tools:
- **`manage_task` Actions**:
  - `list`: Returns running background processes, PIDs, task identifiers, and log file URIs.
  - `status`: Queries execution state (`running`, `completed`, `failed`).
  - `kill`: Sends termination signals to running child processes.
  - `send_input`: Pushes interactive input to a running task's `stdin`.
- **The Reactive Wakeup Invariant**:
  - **Critical Platform Semantic**: In Antigravity 2.0, background tasks automatically emit a system event upon completion that resumes the agent turn.
  - **Empirical Anti-Pattern**: Agents trained on standard LLM paradigms frequently execute polling loops (calling `manage_task(Action='status')` 10–50 times in a row). This wastes tokens, saturates the context window, and risks context cliff degradation. Platform-compliant agents launch background tasks and immediately halt tool calls to await reactive resumption.

### 3.3 Terminal Multiplexer Subsystem (`run_command`)
Shell execution within Antigravity 2.0 is handled through a persistent pseudo-terminal multiplexer:
- **Parameters**:
  - `CommandLine` (required): Command string executed via `bash -c`.
  - `Cwd` (required): Absolute path to working directory.
  - `RunPersistent` (boolean): When `true`, executes inside a persistent terminal shell instance that preserves shell environment variables across separate calls.
  - `RequestedTerminalID` (string): Reuses an established persistent terminal session.
  - `IsDaemon` (boolean): Flags long-running processes (development servers, watchers, tunnels) that are not expected to terminate autonomously.
  - `WaitMsBeforeAsync` (integer, max 10,000ms): Synchronous wait threshold. Commands terminating within this threshold return their output immediately; commands exceeding it are cleanly transitioned to background tasks.
- **Execution Invariants**:
  - Automatically executed with `PAGER=cat` to prevent pagination hangs.
  - Commands must execute non-interactively; interactive prompts without redirection hang the terminal bridge until timeout.

### 3.4 Artifacts Architecture
Artifacts represent persistent, structured deliverables stored under `<appDataDir>/brain/<conversation-id>/`:
- **File Structure**:
  - `task.md`: Living task checklist updated across turns.
  - `implementation_plan.md`: Proposed architectural plan presented for operator approval.
  - `walkthrough.md`: Verification evidence, test logs, and changes completed.
  - `scratch/`: Unindexed, ephemeral workspace for throwaway scripts, test logs, and temporary data.
- **Metadata Contract**:
  ```json
  {
    "UserFacing": true,
    "RequestFeedback": true,
    "Summary": "Concise multi-line architectural overview"
  }
  ```
- **Progressive UI Presentation**: Artifacts are displayed in dedicated split-pane tabs in the desktop interface, separating high-level deliverables from raw chat transcripts.

### 3.5 Reactive Notifications & Scheduling Subsystem (`schedule`)
The platform supports asynchronous temporal triggers:
1. **One-Shot Timers (`DurationSeconds`)**: Fires after an elapsed interval. Supports early cancellation via `TimerCondition`:
   - `'never'`: Unconditionally fires after elapsed duration.
   - `'any'`: Cancels if any message or task event arrives before expiration.
   - `<task-id>`: Cancels if the specified task ID completes before the timer expires.
2. **Recurring Cron (`CronExpression`)**: Standard 5-field cron syntax (`*/5 * * * *`). Dispatches scheduled prompts into the agent conversation loop.
   - `IsDaemon=false`: Active polling/monitoring for current task completion.
   - `IsDaemon=true`: Standing background job that outlives the current task.

---

## 4. Surface Deconstruction: Official Python SDK (`google-antigravity`)

The official Python SDK (`google-antigravity`, imported via `google.antigravity`) allows embedding the full agent lifecycle into custom services, external orchestrators, and automated evaluation harnesses.

```
+----------------------------------------------------------------------------------------------------+
|                                    Python SDK Architecture                                         |
|                                                                                                    |
|  +----------------------------------------------------------------------------------------------+  |
|  |                                            Agent                                             |  |
|  |  * Async Context Manager (`async with Agent(config) as agent:`)                              |  |
|  |  * Binary & Runtime Discovery                                                                |  |
|  |  * Lifecycle Hook & Policy Orchestration                                                     |  |
|  +----------------------------------------------+-----------------------------------------------+  |
|                                                 |                                                  |
|                                                 v                                                  |
|  +----------------------------------------------------------------------------------------------+  |
|  |                                         Conversation                                         |  |
|  |  * Trajectory State & Message History Accumulation                                           |  |
|  |  * Streaming Interface (`response = await agent.chat(...)`)                                  |  |
|  |  * Context Compaction Management (`CompactionConfig(token_threshold)`)                       |  |
|  |  * Cumulative Token Telemetry (`agent.conversation.total_usage`)                             |  |
|  +----------------------------------------------+-----------------------------------------------+  |
|                                                 |                                                  |
|                                                 v                                                  |
|  +----------------------------------------------------------------------------------------------+  |
|  |                                      Connection Strategy                                     |  |
|  |  * `LocalConnectionStrategy`: Gemini API / Vertex AI Enterprise                              |  |
|  |  * `LiteRTConnectionStrategy`: On-device inference via LiteRT-LM (Gemma 4 26B)                |  |
|  |  * `LocalOpenAIConnectionStrategy`: OpenAI-compatible servers (Ollama, LM Studio)             |  |
|  +----------------------------------------------+-----------------------------------------------+  |
+----------------------------------------------------------------------------------------------------+
```

### 4.1 Core Architecture: The Three Pillars
1. **`Agent`**: The primary entry point. Manages environment discovery, child process orchestration (the language server binary), tool wiring, hook registration, and security policies.
2. **`Conversation`**: Represents the stateful trajectory. Manages message history, handles context compaction when token thresholds are exceeded, and exposes token usage metadata (`total_usage`).
3. **`Connection`**: Transport abstraction decoupling the agent API from the model inference backend.

### 4.2 Configuration Model (`LocalAgentConfig`)

```python
from google.antigravity import Agent, LocalAgentConfig, types
from google.antigravity.hooks import policy

config = LocalAgentConfig(
    model="gemini-3.8-flash",                               # Model target (default: gemini-3.8-flash)
    system_instructions="Authoritative System Prompt",      # Root system instruction
    app_data_dir="/absolute/path/to/storage",               # Artifact storage override
    capabilities=types.CapabilitiesConfig(
        agent_behavior=types.AgentBehavior.AUTONOMOUS,      # AUTONOMOUS vs INTERACTIVE
        enable_subagents=True,                              # Hierarchical subagent spawning
        max_subagent_depth=3,                               # Subagent nesting ceiling
        allowed_subagents=["researcher", "executor"],       # Subagent name allowlist
        run_command_config=types.RunCommandConfig(
            enable_sandbox=True,                            # OS-level command sandboxing
            enable_daemons=True                             # Support background daemons
        )
    ),
    budget_config=types.BudgetConfig(
        max_model_calls=50,                                 # Turn limits
        max_tool_calls=150,                                 # Tool limit ceiling
        max_total_tokens=500_000                            # Proactive token budget
    ),
    compaction_config=types.CompactionConfig(
        token_threshold=100_000                             # Context compaction trigger threshold
    ),
    policies=[
        policy.workspace_only(),                            # Confine file tools to workspace
        policy.confirm_run_command()                        # Default safe execution policy
    ],
    env={"PATH": "/usr/local/bin:/usr/bin"}                 # Subprocess environment overrides
)
```

### 4.3 Declarative Safety Policies (`google.antigravity.hooks.policy`)
The SDK evaluates tool calls against a strict **9-level priority hierarchy** (highest to lowest), short-circuiting on first match:
1. **Specific Deny**: `policy.deny("run_command")`
2. **Specific Ask**: `policy.ask_user("run_command", handler=my_handler)`
3. **Specific Allow**: `policy.allow("view_file")`
4. **Prefix Wildcard Deny**: `policy.deny("mcp_server/*")`
5. **Prefix Wildcard Ask**: `policy.ask_user("mcp_server/*", handler=my_handler)`
6. **Prefix Wildcard Allow**: `policy.allow("mcp_server/*")`
7. **Global Wildcard Deny**: `policy.deny_all()` / `policy.deny("*")`
8. **Global Wildcard Ask**: `policy.ask_user("*", handler=my_handler)`
9. **Global Wildcard Allow**: `policy.allow_all()` / `policy.allow("*")`

- **Predicate Evaluation (`when`)**: Policies can inspect tool arguments via lambda predicates:
  ```python
  policy.deny("run_command", when=lambda args: "rm -rf" in args.get("CommandLine", ""))
  ```
- **Fail-Closed Invariant**: If a predicate raises an unhandled exception during evaluation, the policy **fails closed**, treating the predicate as a match and enforcing the restrictive decision.

### 4.4 Programmatic Execution & Streaming Interface
```python
async with Agent(config) as agent:
    # Non-blocking turn dispatch returning async streaming response
    response = await agent.chat("Execute test verification suite")

    # Stream text tokens
    async for token in response:
        sys.stdout.write(token)

    # Stream model thinking / reasoning deltas
    async for thought in response.thoughts:
        print(f"[Reasoning] {thought}")

    # Stream strongly-typed tool call events
    async for call in response.tool_calls:
        print(f"[Tool Dispatch] {call.name} -> {call.args}")

    # Inspect exact cumulative token telemetry
    usage = agent.conversation.total_usage
    print(f"Prompt: {usage.prompt_token_count}, Thoughts: {usage.thoughts_token_count}, Total: {usage.total_token_count}")
```

---

## 5. Surface Deconstruction: Lifecycle Hooks Engine

The Lifecycle Hooks engine provides the highest-leverage developer extension mechanism in Antigravity. Unlike rules or skills that rely on probabilistic model compliance, hooks execute **deterministic code outside the context window**, intercepting execution points with zero token cost.

Hooks are configured either declaratively in `hooks.json` (supported across CLI, Antigravity 2.0, and IDE) or programmatically via Python decorators in the SDK.

### 5.1 The Five Core Lifecycle Events

| Event | Matcher Target | Execution Point | Primary Use Case |
| :--- | :--- | :--- | :--- |
| **`PreToolUse`** | Regex on Tool Name (`run_command`, `view_file\|grep_search`, `*`) | Before tool dispatch | Argument validation, dangerous command blocking, command rewriting via `overwrite`, loop tripping. |
| **`PostToolUse`** | Regex on Tool Name | Immediately after tool execution completes | Error classification, output size auditing, automated telemetry harvesting, log truncation. |
| **`PreInvocation`** | Flat array (no matcher) | Before prompt dispatch to Gemini | Context injection, ephemeral reminder insertion, dynamic rule gating. |
| **`PostInvocation`** | Flat array (no matcher) | After Gemini generates tool calls | Tool call inspection, forcing loop continuation (`force_continue`), premature halt prevention. |
| **`Stop`** | Flat array (no matcher) | When the trajectory reaches fully idle | Completion fencing, test verification enforcement, preventing premature victory claims. |

### 5.2 JSON Protocol Specification (camelCase Protojson over Stdio)

Every hook configured in `hooks.json` receives a JSON payload on `stdin` and must emit its result as JSON on `stdout`.

#### Common Ingress Metadata (Present on all events)
```json
{
  "conversationId": "270b7abc-9b59-4f50-9c49-de3ed7e04f06",
  "workspacePaths": ["/workspace/psl-agy-harness"],
  "transcriptPath": "~/.gemini/antigravity/brain/270b7abc.../transcript.jsonl",
  "artifactDirectoryPath": "~/.gemini/antigravity/brain/270b7abc.../",
  "modelName": "auto"
}
```

#### 1. `PreToolUse` Contract
- **Ingress (`stdin`)**:
  ```json
  {
    "toolCall": {
      "name": "run_command",
      "args": {
        "CommandLine": "git diff | grep TODO",
        "Cwd": "/workspace/psl-agy-harness"
      }
    },
    "stepIdx": 42,
    ...commonMetadata
  }
  ```
- **Egress (`stdout`)**:
  ```json
  {
    "decision": "allow",
    "reason": "Normalized git pipeline to defend against false-failure exit code 1",
    "overwrite": {
      "CommandLine": "git diff | grep TODO || true"
    },
    "permissionOverrides": ["command(git diff)"]
  }
  ```
  - **`decision`**: `"allow"` (execute), `"deny"` (abort with error to agent), `"ask"` (prompt user), `"force_ask"` (prompt user ignoring permissions cache).
  - **`overwrite`**: **Shallow top-level dictionary replacement**. Replaces matching keys in the tool arguments before execution occurs. The rewritten arguments are what actually run and what get recorded in the transcript.

#### 2. `PostToolUse` Contract
- **Ingress (`stdin`)**:
  ```json
  {
    "stepIdx": 42,
    "error": "exit status 1",
    ...commonMetadata
  }
  ```
- **Egress (`stdout`)**:
  ```json
  {}
  ```
  *(Returns an empty JSON object `{}`. PostToolUse is designed for external side-effects: telemetry logging, cache invalidation, state updates).*

#### 3. `PreInvocation` Contract
- **Ingress (`stdin`)**:
  ```json
  {
    "invocationNum": 4,
    "initialNumSteps": 18,
    ...commonMetadata
  }
  ```
- **Egress (`stdout`)**:
  ```json
  {
    "injectSteps": [
      {
        "ephemeralMessage": "High-Resolution Reminder: Verify unit test exit codes before declaring milestone complete."
      }
    ]
  }
  ```
  - Supported `injectSteps` types: `{"ephemeralMessage": "..."}`, `{"userMessage": "..."}`, `{"toolCall": {"name": "...", "args": {...}}}`.

#### 4. `PostInvocation` Contract
- **Ingress (`stdin`)**: Common metadata + `invocationNum`, `initialNumSteps`.
- **Egress (`stdout`)**:
  ```json
  {
    "injectSteps": [],
    "terminationBehavior": "force_continue"
  }
  ```
  - `terminationBehavior`: `"force_continue"` (forces another turn), `"terminate"` (aborts loop), `""` (default).

#### 5. `Stop` Contract
- **Ingress (`stdin`)**:
  ```json
  {
    "executionNum": 1,
    "terminationReason": "model_stop",
    "error": "",
    "fullyIdle": true,
    ...commonMetadata
  }
  ```
- **Egress (`stdout`)**:
  ```json
  {
    "decision": "continue",
    "reason": "PSL Completion Fence: Verification tests have not passed. Run pytest before finishing."
  }
  ```
  - `decision`: `"continue"` blocks termination and injects `reason` into the context window as a high-priority system prompt. Any other value allows the agent to terminate cleanly.

---

## 6. Surface Deconstruction: Model Context Protocol (MCP) Boundaries

Antigravity integrates with the Model Context Protocol (MCP) to provide clean boundaries between the agent core and external tool providers.

### 6.1 Transports
1. **Stdio Transport (Local Process)**:
   - Language Server spawns the target executable directly and communicates over standard input/output using JSON-RPC.
   - Configuration defines `command`, `args`, and `env` dictionaries.
   - Lifecycle is bound to the parent session.
2. **Streamable HTTP / SSE Transport (Remote Service)**:
   - Connects to remote MCP endpoints over HTTP using Server-Sent Events (SSE).
   - Configuration defines `serverUrl` and optional authentication `headers`.

### 6.2 Tool Filtering (Allowlist / Denylist)
To prevent tool exposure from saturating the context window and triggering context cliff degradation, MCP server configurations support strict tool filtering:
```python
stdio_server = types.McpStdioServer(
    name="knot_mesh_service",
    command="python3",
    args=["-m", "knot.mcp_server"],
    enabled_tools=["mesh_node_status", "mesh_exec"],   # Allowlist: ONLY these 2 tools exposed
    # disabled_tools=["dangerous_wipe"]                # Denylist: Alternative mutually-exclusive filter
)
```

### 6.3 FastMCP Compliance & Boundary Invariants
- **Identifier Safety**: FastMCP requires all tool names and parameter keys to be valid Python identifiers (`^[a-zA-Z_][a-zA-Z0-9_]*$`). Any MCP tool emitting non-compliant identifiers fails schema ingestion.
- **Synchronous Blocking Boundary**: MCP tool calls execute synchronously from the agent loop's perspective. Long-running remote calls must implement their own internal async queuing or be offloaded to background daemons.
- **Safety Policy Binding**: By default, standard SDK policies allow MCP tool calls while restricting `run_command`. Under strict deny-by-default setups (`policy.deny_all()`), MCP servers must be explicitly granted via overloaded policy helpers (`policy.allow(mcp_server)`).

---

## 7. Empirical Gap Analysis: Audited Workstation Failures vs Platform Capabilities

Our empirical audit analyzed **348 developer sessions, 140,005 trajectory steps, 64,065 tool calls, and 2,232 tool failures** recorded on this workstation (`docs/taxonomy/workstation-audit-report.md`). 

Below is the definitive gap analysis mapping these breakdowns against Antigravity platform capabilities, categorizing the exact architectural remedy for each failure mode.

```
+----------------------------------------------------------------------------------------------------+
|                                    Empirical Failure Distribution                                  |
|                                                                                                    |
|  [run_command Failures: 98.4% (2,192 errors)]                                                     |
|  * Exit Code 1 (1,544): Benign non-zero search / diff matches                                      |
|  * Exit Code 2 (245): Shell syntax / option misuse                                                 |
|  * Exit Code 127 (143): Binary not found in PATH                                                   |
|  * Exit Code 255 (72): SSH remote node connection timeouts                                         |
|                                                                                                    |
|  [Tool Thrashing Loops: 5,773 occurrences]                                                         |
|  * view_file (3,951): Consecutive redundant file reads                                            |
|  * grep_search (625): Identical un-evolved query loops                                             |
|  * manage_task (300): Polling loops ignoring reactive wakeups                                     |
|  * run_command (360): Repeating identical failing commands                                         |
|                                                                                                    |
|  [The 200+ Step Context Cliff]                                                                     |
|  * 1-50 steps: 0.35 errors, 0.04 interventions                                                     |
|  * 200+ steps: 20.54 errors (20x surge), 16.32 operator interventions (40x surge)                 |
|                                                                                                    |
|  [Human Operator Interventions: 1,690 occurrences]                                                 |
|  * Stop & Hold Fences (69): Operator catching runaway agents                                       |
|  * Trajectory Drift (4): Correcting divergence from architectural plan                             |
|  * Premature Victory Claims: Halting before verification tests run                                |
+----------------------------------------------------------------------------------------------------+
```

---

### Gap Matrix: Failure Mode vs. Architectural Layer

| Empirical Failure Mode | Root Cause | Layer 1: Under-Utilized Native Feature | Layer 2: Lifecycle Hook Requirement (`hooks.json`) | Layer 3: MCP Tool / Skill Requirement |
| :--- | :--- | :--- | :--- | :--- |
| **Exit Code 1 (1,544 failures)** | Benign commands (`grep`, `diff`) exiting 1 on zero matches; agent treats as fatal error and panics. | Use CLI/SDK structured commands; avoid raw subshells. | **`PreToolUse` Hook (`command_safety`)**: Regex match command string, append `\|\| true` via `overwrite.CommandLine` on pattern-search pipelines. | Rule invariant: Document pattern matching non-zero exits as benign in `AGENTS.md`. |
| **Exit Code 127 (143 failures)** | Missing binaries, uninstalled dependencies, broken `PATH`. | Configure `LocalAgentConfig(env={"PATH": ...})` or run `agy install`. | **`PreToolUse` Hook**: Extract binary executable token (`which <bin>`); deny with actionable error if missing. | Custom Setup Skill: Pre-flight environment verifier. |
| **Exit Code 255 (72 failures)** | Remote Knot mesh calls hanging on offline nodes (laptop, ally, steamdeck) without timeouts. | Pass `-o ConnectTimeout=5` on all SSH commands. | **`PreToolUse` Hook**: Match `^ssh\s+` and enforce `-o ConnectTimeout=5 -o BatchMode=yes` via `overwrite`. | **Knot Mesh MCP Tool**: Offload remote execution to a dedicated MCP server with health checks. |
| **Interactive TUI Hangs** | Commands launching `nano`, `vim`, or unpiped interactive CLIs, freezing session. | Use CLI `--dangerously-skip-permissions` and `RunCommandConfig(enable_sandbox=True)`. | **`PreToolUse` Hook (`command_safety`)**: Inspect executable; hard-deny interactive TUI tools. | Rule invariant: Enforce non-interactive flags (`PAGER=cat`, `--batch`). |
| **`view_file` Thrashing (3,951 calls)** | Agent re-reading identical file ranges across consecutive steps without state retention. | Use progressive disclosure and persistent context. | **`PreToolUse` Hook (`anti_loop_hook`)**: Track signature `(name, args)`; after 2 consecutive identical calls, deny with message to consult context. | Skill caching guideline: Advise model to retain read buffers. |
| **`manage_task` Polling (300 calls)** | Agent polling `Action='status'` in a loop instead of awaiting reactive notification. | **Native Reactive Wakeup**: Stop calling tools and await completion notification from runtime. | **`PreToolUse` Hook**: Deny `manage_task(Action='status')` if called consecutively without intervening task events. | Rule invariant: Forbid manual polling loops in `AGENTS.md`. |
| **`grep_search` Thrashing (625 calls)** | Agent repeating identical failed query without broadening pattern or checking case. | Use ripgrep flags properly; leverage semantic code search. | **`PreToolUse` Hook (`anti_loop_hook`)**: Deny identical consecutive regex queries; force query evolution. | Skill: Multi-stage search runbooks. |
| **The 200+ Step Context Cliff** | Massive tool outputs (10k+ lines of build logs) flooding context, causing 20x error surge. | Configure `CompactionConfig(token_threshold=50000)` and `BudgetConfig(max_total_tokens)`. | **`PostToolUse` Hook**: Truncate tool output buffers exceeding 50 lines / 4KB before recording to transcript. | Pipeline automation: Pipe commands through `head -n 50` or `wc -l`. |
| **Premature Victory Claims** | Agent declaring completion without running tests or verifying exit codes. | Configure SDK `agent_behavior=INTERACTIVE` with mandatory approval gates. | **`Stop` Hook (`completion_fence`)**: Inspect session state; if verification test suite has not run and passed, return `decision="continue"`. | Skill: Verification and testing checklist runbook. |
| **Stop & Hold Fences (69 operator halts)** | Operator forced to intervene manually to halt runaway destructive actions. | Apply restrictive `policy.workspace_only()` and `policy.confirm_run_command()`. | **`PreToolUse` Hook**: Intercept destructive patterns (`rm -rf /`, `mkfs`, `git reset --hard`) and enforce `force_ask`. | Rule invariant: High-risk confirmation gates. |

---

## 8. The Three Architectural Buckets: Where Capabilities Belong

To establish clean engineering boundaries in `psl-agy-harness`, platform responsibilities are cleanly bifurcated across three implementation tiers:

```
+----------------------------------------------------------------------------------------------------+
|                                  Three-Tier Architecture Model                                     |
|                                                                                                    |
|  [Tier 1: Native Platform Primitives]                                                              |
|  * Reactive Task Notification Wakeups (zero-polling concurrency)                                   |
|  * Built-in OS Command Sandboxing (cgroups / namespaces)                                           |
|  * Context Compaction Thresholds (CompactionConfig)                                                |
|  * MCP Tool Allowlist/Denylist Filtering (context protection)                                      |
|  * Structured NDJSON Streaming Protocol (--input-format stream-json)                                |
|                                                                                                    |
|  [Tier 2: Lifecycle Hooks Engine (hooks.json)]                                                     |
|  * PreToolUse: Deterministic command safety, destructive pattern blocking                          |
|  * PreToolUse: Shallow argument rewrite (overwrite) for PAGER=cat, timeouts, || true               |
|  * PreToolUse: Anti-loop signature tracking (denying 3+ consecutive identical calls)                |
|  * PostToolUse: Output truncation and log size governance                                          |
|  * Stop: Trajectory completion gating (blocking exit until tests pass)                             |
|                                                                                                    |
|  [Tier 3: MCP Servers & Custom Skills]                                                             |
|  * Knot Mesh MCP: Remote node hardware bridging, SSH pooling, failover                             |
|  * Linda Tuplespace MCP: Out-of-band multi-agent blackboard coordination                            |
|  * Audit Toolkit Skill: Telemetry analysis, failure classification, session reporting              |
|  * Subagent Ladder Protocol: Staged multi-agent pipelines (Executioner -> Hammer -> Auditor)       |
+----------------------------------------------------------------------------------------------------+
```

### Tier 1: Under-Utilized Native Platform Features
These capabilities are implemented directly inside the Antigravity engine and require zero custom hook scripts—only proper configuration:
1. **Reactive Event Wakeup**: Eliminates 300+ `manage_task` loops. Agents do not poll; they launch tasks and await reactive wakeups.
2. **Context Compaction Governance**: Eliminates the 200+ step context cliff by setting `compaction_config=CompactionConfig(token_threshold=50000)` in SDK configurations.
3. **MCP Tool Filtering**: Shrinks system prompt token overhead by declaring `enabled_tools` on each MCP server in `LocalAgentConfig` or `mcp_config.json`.
4. **Non-Interactive Batch Automation**: Using `agy -p --effort high --dangerously-skip-permissions` ensures headless workflows execute without human hang gates.
5. **Declarative 9-Level Safety Policies**: Enforcing `policy.workspace_only()` prevents stray modifications outside the repository root.

### Tier 2: Lifecycle Hooks Responsibilities (`hooks.json`)
Deterministic interception where probabilistic prompt steering is insufficient:
1. **Pre-flight Argument Rewriting (`PreToolUse.overwrite`)**:
   - Rewriting `git diff` to include `PAGER=cat`.
   - Appending `|| true` to pattern searches prone to benign Exit Code 1.
   - Injecting `-o ConnectTimeout=5` into SSH command strings.
2. **Anti-Loop Circuit Breakers (`PreToolUse`)**:
   - Caching tool call signatures `(name, args)`.
   - Denying repetitive calls (threshold >= 3) to break model thrashing on `view_file` and `grep_search`.
3. **Destructive Safety Gates (`PreToolUse`)**:
   - Hard-blocking hazardous shell commands (`rm -rf /`, raw disk writes).
   - Upgrading destructive operations to `"force_ask"`.
4. **Context Flood Prevention (`PostToolUse`)**:
   - Auditing output sizes of `run_command` and truncating context-exploding outputs.
5. **Completion Fences (`Stop`)**:
   - Gating trajectory termination by checking test pass records before allowing `"allow_stop"`.

### Tier 3: MCP Servers & Custom Skills
Complex, domain-specific state orchestration and procedural execution:
1. **Hardware Mesh Remote Orchestration (Knot Mesh MCP)**: Encapsulates multi-node execution (Desktop Anchor, Laptop CUDA, Steam Deck) behind structured tools with built-in health checks and timeout recovery, eliminating fragile raw SSH terminal calls.
2. **Distributed Agent Blackboard (Linda Tuplespace MCP)**: Provides tuple coordination (`out`, `in`, `rd`) for multi-agent workflows without context window pollution.
3. **Audit & Diagnostics Toolkit (Skill)**: Mimes and classifies workstation telemetry, generating actionable failure modes and trajectory analytics.
4. **High-Resolution Engineering Runbooks (Rules & Skills)**: Providing progressive procedural knowledge for complex refactoring, ladder workflows, and architectural reviews.

---

## 9. Definitive Platform Surface Comparison

| Feature / Dimension | Antigravity CLI (`agy`) | Antigravity 2.0 Desktop | Official Python SDK | Lifecycle Hooks (`hooks.json`) |
| :--- | :--- | :--- | :--- | :--- |
| **Primary Consumer** | Terminal developer, CI/CD, batch runners | GUI developer, pair programming | Services, custom agent harnesses, evaluators | Safety guards, linters, policy enforcement |
| **Execution Modality** | Interactive TUI, Batch `-p`, NDJSON stream | Visual Electron app, Chat Canvas | Programmatic async context manager | Synchronous hook subprocesses (stdio) |
| **Reasoning Control** | `--effort low\|medium\|high` | Global & Project Settings menu | Endpoint model options / budget configs | N/A (runs before/after inference) |
| **Tool Execution Safety** | `--dangerously-skip-permissions`, `--sandbox` | Global/Project Tool Policy (`strict`, `sandbox`) | 9-level declarative policy hierarchy (`policy.*`) | `PreToolUse` decision: `allow`, `deny`, `ask`, `force_ask` |
| **Tool Argument Modification**| None (flags only) | None | SDK wrapper functions | **`PreToolUse` shallow `overwrite`** |
| **Context Management** | Native compaction | Visual tab separation, progressive artifacts | `CompactionConfig(token_threshold)` | `PostToolUse` output truncation |
| **Task Concurrency** | Background daemon (`remote-control`) | `manage_task` pane + reactive wakeup bus | `asyncio` event loop + custom tasks | Can inspect task state via external scripts |
| **Completion Fencing** | Exit code / schema validation | Manual operator prompt | Budget and stop hook delegates | **`Stop` hook `decision="continue"`** |

---

## 10. Architectural Recommendations for `psl-agy-harness`

Based on this surface mapping and empirical gap analysis, the `psl-agy-harness` project should adopt the following canonical architecture:

1. **Standardize on `hooks.json` for Anti-Loop & Safety Invariants**:
   - Maintain `harness/hooks/anti_loop_hook.py` targeting `view_file|grep_search|run_command|manage_task` to prevent the 5,773 audited loop calls.
   - Maintain `harness/hooks/command_safety_hook.py` with `overwrite` rewriting to eliminate Exit Code 1 false-failures and Exit Code 255 SSH timeouts.
   - Deploy `harness/hooks/completion_fence_hook.py` under the `Stop` event to eliminate premature victory claims without test execution.

2. **Leverage Native Reactive Wakeups in Agent Rules**:
   - Update `AGENTS.md` to strictly forbid polling `manage_task(Action='status')` in loops, documenting that the Antigravity engine resumes execution reactively.

3. **Deploy the Python SDK for Benchmark Harnesses**:
   - Utilize `LocalAgentConfig().eval()` with `CompactionConfig(token_threshold=50000)` and `RunCommandConfig(enable_sandbox=True)` for all automated regression evaluations.

4. **Encapsulate Knot Mesh Execution Behind an MCP Server**:
   - Transition all remote cluster commands from raw terminal SSH calls into a dedicated Stdio MCP server (`knot-mesh-mcp`), isolating connection timeouts and network retries from the agent context window.
