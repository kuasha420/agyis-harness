<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Antigravity Platform Surface Mapping: Deconstruction & Empirical Gap Analysis

**Document**: Canonical Architecture & Surface Mapping Specification  
**Project**: Agyis Harness for Google Antigravity™ (`agyis-harness`)  
**Publisher**: Purrfect Software Limited (PSL)  
**License**: Apache-2.0  
**Status**: Canonical First-Principle Surface & Protocol Reference  
**Empirical Baseline**: Grounded in [`../taxonomy/empirical-baselines.md`](../taxonomy/empirical-baselines.md) (`1,734` classified sessions / `2,875` live sessions)

---

## Executive Summary

Google Antigravity provides an extensible multi-tier agent execution runtime across three primary developer surfaces:

1. **The Antigravity CLI (`agy`)**: Interactive TUI, non-interactive batch/print execution, structured streaming via NDJSON (`stream-json`), and terminal daemon management.
2. **The Antigravity 2.0 Desktop Platform**: Electron-based orchestrator, Language Server Connect RPC introspection, HTML auxiliary generative UI, background task supervision (`manage_task`), terminal multiplexer, reactive scheduling (`schedule`), 9 system slash commands, and 4 hidden invokable subagent `TypeName`s.
3. **The Official Python SDK (`google-antigravity`)**: The three-pillar architecture (`Agent`, `Conversation`, `Connection` / `AgentClient`), capability configurations, 9-level declarative safety policies, and session leasing.
4. **The Lifecycle Hooks Engine (`hooks.json` & SDK Hooks)**: Deterministic `PreToolUse`, `PostToolUse`, `PreInvocation`, `PostInvocation`, and `Stop` interception outside the token context window (detailed contracts in [`lifecycle-hooks.md`](lifecycle-hooks.md)).
5. **Model Context Protocol (MCP) Boundaries & Extension Packaging**: Stdio vs. Streamable HTTP/SSE transports, tool filtering allowlists/denylists, official plugin manifests (`plugin.json`), 5-tier discovery precedence, and context budget caps.

The empirical gap analysis in §7 matches these platform capabilities against audited failure distributions in [`../taxonomy/empirical-baselines.md`](../taxonomy/empirical-baselines.md) (with historical cohort context preserved in [`../archive/taxonomy/workstation-audit-report.md`](../archive/taxonomy/workstation-audit-report.md)).

---

## 1. Platform Topology, Extension Manifests & Discovery Precedence

```
+----------------------------------------------------------------------------------------------------+
|                                    Antigravity Platform Runtime                                    |
|                                                                                                    |
|  +-----------------------------+  +-------------------------------+  +--------------------------+  |
|  |     Antigravity CLI (agy)   |  |   Antigravity 2.0 Desktop     |  |   Official Python SDK    |  |
|  |                             |  |   (Electron / IDE Host)       |  |  (google-antigravity)    |  |
|  |  * Interactive TUI          |  |  * Chat Canvas & Slash Cmds   |  |  * Agent / AgentClient   |  |
|  |  * Batch Print (-p)         |  |  * Connect RPC & Aux GenUI    |  |  * Conversation State    |  |
|  |  * Stream NDJSON Protocol   |  |  * Reactive Background Tasks  |  |  * Strategy Transports   |  |
|  |  * Subcommands (mcp, plugin)|  |  * Terminal Multiplexer (TUI) |  |  * Declarative Policies   |  |
|  +--------------+--------------+  +---------------+---------------+  +------------+-------------+  |
+-----------------|---------------------------------|-------------------------------|----------------+
                  |                                 |                               |
                  +---------------------------------+-------------------------------+
                                                    |
                                                    v
+----------------------------------------------------------------------------------------------------+
|                      Core Language Server & Cortex Loop (Dual-Plane Protobufs)                     |
|                                                                                                    |
|  [PreInvocation Hook] -> [Model Inference (Gemini)] -> [PostInvocation Hook]                      |
|                                         |                                                          |
|                                         v (Tool Call Generated)                                    |
|  [PreToolUse Hook]    -> [Safety Policy Evaluation] -> [Tool Dispatch] -> [PostToolUse Hook]       |
|  (Gate / Arg Overwrite)  (9-Level Ladder Check)       (Built-in / MCP)    (Audit / 2KB Compaction) |
|                                                                                                    |
|  [Trajectory Idle]    -> [Stop Hook Gating] (continue vs allow_stop; 2-block safety valve)         |
+---------------------------------------------------+------------------------------------------------+
                                                    |
         +------------------------------------------+----------------------------------------+
         |                                          |                                        |
         v                                          v                                        v
+-----------------------+              +--------------------------+             +--------------------+
|  Built-in Tools       |              |  Model Context Protocol  |             |  Custom Extensions |
|  * run_command        |              |  (FastMCP / JSON-RPC)    |             |  * Skills / Rules  |
|  * view_file          |              |  * Stdio Subprocess      |             |  * Slash Commands  |
|  * replace_file_content              |  * Streamable HTTP / SSE |             |  * Subagent Trees  |
|  * manage_task        |              |  * Tool Filtering Filter |             |  * Official Plugins|
+-----------------------+              +--------------------------+             +--------------------+
```

### 1.1 Official Plugin Directory Layout & Manifest Schema (`plugin.json`)

An official Antigravity plugin bundles manifests, MCP definitions, lifecycle hooks, rules, agents, and modular skills into a single distributable root:

```text
<plugin-root>/
├── plugin.json       # Required: Manifest metadata marker
├── mcp_config.json   # Optional: Exposes stdio / HTTP MCP servers
├── hooks.json        # Optional: Registers lifecycle hooks (ADR-022..033)
├── agents/           # Optional: Dual-mode agent personas (*.md)
├── rules/            # Optional: Merged into active rules (AGENTS.md)
│   └── GLOBAL_AGENTS.md
└── skills/           # Optional: Progressive-disclosure skill definitions
    └── <skill-name>/
        └── SKILL.md
```

```json
{
  "name": "agyis-harness",
  "displayName": "Agyis Harness for Google Antigravity™",
  "version": "1.0.0-rc10",
  "description": "Empirical audit pipeline and reference extension harness for Google Antigravity™",
  "author": { "name": "Purrfect Software Limited (PSL)" },
  "license": "Apache-2.0",
  "keywords": ["antigravity", "harness", "telemetry", "audit", "gemini"],
  "disabled": false
}
```

**Plugin Identity & Activation State Contract**:
- Runtime plugin identity is keyed by the **installed directory basename (`<dir>`)**, NOT the `name` field inside `plugin.json`.
- Active enable/disable overrides live in `~/.gemini/config/config.json` under `plugins.<dir>.enabled` (boolean). Setting `plugins.<dir>.enabled: true` overrides `"disabled": true` declared in `plugin.json`.

### 1.2 Native 5-Tier Discovery Precedence & Override Hierarchy

Antigravity evaluates extensions across **5 native discovery tiers** (highest to lowest precedence):

1. **Workspace Project Level**: Discovered hierarchically walking upward from `CWD` to the `.git` repository root across `.agents/`, `.agent/`, `_agents/`, and `_agent/` (highest precedence; `.agent/` is legacy and harmonized into `.agents/` via `agyis harmonize`).
2. **Workspace Declared Configs**: Explicit registrations declared in workspace `skills.json` or `plugins.json`.
3. **Global User Directory**: Workstation-wide customizations under `~/.gemini/config/` (rules, skills, agents, and installed plugins in `~/.gemini/config/plugins/`).
4. **Built-in Platform Bundles**: Embedded default skills and bundles shipped inside the Antigravity runtime (`/builtin/skills/`).
5. **Global Declared Configs**: Explicit global manifest registrations under `~/.gemini/config/*.json`.

#### Coexistence & Override Matrix (ADR-030)

| Component | Global Plugin / User Tier | Workspace Local Tier (`<project>/.agents/`) | Precedence & Resolution Semantics |
| :--- | :--- | :--- | :--- |
| **Modular Skills** | `~/.gemini/config/skills/` or plugin `skills/` | `<project>/.agents/skills/<skill>/SKILL.md` | **Workspace > User > Plugin**: Local skills shadow global names; workspace skills matching plugin skills should be pruned or symlinked (`agyis skills --prune-duplicates`). |
| **Specialist Agents** | `~/.gemini/config/agents/<name>.md` or plugin `agents/` | `<project>/.agents/agents/<name>.md` | **Workspace > User > Plugin**: Local agent definition overrides global persona while inheriting declared capability bundles. |
| **Agent Rules** | `~/.gemini/config/AGENTS.md` & `rules/*.md` | `<project>/AGENTS.md` & `.agents/rules/*.md` | **Workspace > User > Plugin**: Additive rule composition bounded by platform size and token budgets. |
| **Tooling & Runtimes** | System `$PATH`, `uv` user Python | Project `.venv`, `node_modules` | `agyis` and lifecycle hooks auto-promote project `.venv/bin/python` or `uv` CPython >= 3.12. |
| **Lifecycle Hooks** | Plugin/global `hooks.json` | Project-level `hooks.json` | Deterministic fail-safe stdio subprocesses (`timeout=5s` default in harness). |
| **Git Hygiene** | Global gitignore | Local `.git/info/exclude` | `agyis onboard` / `agyis install` exclude ephemeral local harness state from git porcelain status. |

### 1.3 Platform Rule & Skill Context Budgets

Antigravity enforces strict byte and token ceilings during customization ingestion:
- **Per-Rule File Cap**: `24,000` bytes maximum per individual rule file.
- **Aggregate Rules Token Budget**: `20,000` tokens (`defaultRulesBudget`) across combined user/workspace rules (built-in rules are exempt from this quota).
- **Per-Skill `SKILL.md` Cap**: `24,576` bytes (`24 KB`) maximum; upstream silently truncates oversized `SKILL.md` definitions (`harness` additionally enforces `## Table of Contents` for any `SKILL.md` exceeding `100` lines).
- **Progressive Disclosure & Duplicate Pruning**: Only `name` + `description` frontmatter loads at turn startup (`16` skills = `1,330` inline tokens vs `5` MCP servers = `263,759` schema tokens). Duplicate workspace skill copies shadow global skills and waste `~4,500` redundant tokens per turn until pruned via `agyis skills --prune-duplicates`.

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
For programmatic harnesses (including `agyis-harness` test runners), `stream-json` provides an NDJSON-based interface:
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

- **`agy plugin`**: `list`, `import [source]` (`gemini` or `claude`), `install <target>` (`plugin@marketplace`), `uninstall <name>`, `enable <name>` / `disable <name>`, `validate [path]`, `link <mp> <target>`.
- **`agy mcp`**: `add [flags] <name> <commandOrUrl> [args...]` (`-e`/`--env`, `-H`/`--header`, `-t stdio|http`), `remove <name>`, `list`, `enable <name>` / `disable <name>`.
- **`agy agent` / `agy agents`**: Enumerate available agent personas and configurations.
- **`agy models`**: Query Gemini model targets available to current credentials.
- **`agy remote-control`**: Control background workstation daemon (`start`, `status`, `stop`).
- **`agy mic-serve` / `agy install`**: Stream local microphone audio / bootstrap shell paths and completions.

### 2.5 Language Server Connect RPC & Dual-Plane Protobuf Descriptors

The desktop Language Server exposes an authenticated local Connect RPC endpoint for live discovery of slash commands, skills, and planner configuration:

- **Endpoint**: `POST http://127.0.0.1:<port>/exa.language_server_pb.LanguageServerService/GetSlashCommands`
- **Required Headers**:
  - `Content-Type: application/json`
  - `Connect-Protocol-Version: 1`
  - `x-codeium-csrf-token`: Extracted from `--csrf_token` runtime argument or renderer `window.__APP_CONFIG__.csrfToken`.
- **Request Payload**:
  ```json
  {
    "workspaceUris": ["file:///path/to/workspace"],
    "cascadeConfig": {
      "plannerConfig": { "planModel": "<model-id>" }
    }
  }
  ```
- **Response (`commands[]`)**: Entries contain `info.name`, `info.type` (`SLASH_COMMAND_TYPE_SYSTEM` | `SLASH_COMMAND_TYPE_SKILL`), `info.icon`, `info.modelFacingText`, `title`, and `description`.
- **Dual-Plane Protobuf Architecture (`google3/third_party/jetski/*`)**:
  - `language_server_pb/language_server.proto`: IDE control plane (Connect RPC service, workspace URIs, slash command resolution).
  - `cortex_pb/cortex.proto`: Cortex execution engine (planning configs, step payloads, model routing).
  - `cascade_plugins_pb/cascade_plugins.proto`: Plugin manifests, lifecycle hook contracts, and agent definitions.
  - `reactive_component_pb/reactive_component.proto`: Trajectory steps, token metadata (`field 9`: subfield `2` prompt tokens, subfield `5` cached content tokens), and reactive task events.

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
|  | * Projects Root    |  | * Slash Commands (/boost, /plan)    |  | [HTML Generative UI / Tab]  |  |
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
- **Use Cases**: Live metric cockpits, topology graphs, audit dashboards, interactive approval forms, and component mockups.
- **Contract**: Communication back to the agent is bridged via structured DOM events or clipboard transfers.

### 3.2 Background Task Supervision & The Reactive Wakeup Invariant
The desktop runtime provides an asynchronous execution engine managed via the built-in `manage_task` and `schedule` tools:
- **`manage_task` Actions**:
  - `list`: Returns running background processes, PIDs, task identifiers, and log file URIs.
  - `status`: Queries execution state (`running`, `completed`, `failed`).
  - `kill`: Sends termination signals to running child processes.
  - `send_input`: Pushes interactive input to a running task's `stdin`.
- **The Reactive Wakeup Invariant & Issue #41 Advisory Contract**:
  - **Platform Semantic**: In Antigravity 2.0, background tasks automatically emit a reactive system event upon completion that resumes the agent turn.
  - **Harness Enforcement**: `anti_loop_hook.py` emits a non-blocking **advisory allow** (`{"decision": "allow", "reason": "Advisory: Background tasks notify reactively upon exit. Avoid polling status to conserve steps."}`) on `manage_task(Action='status')`, while hard-denying repeated polling reads of `.system_generated/tasks/` or `.system_generated/logs/` (Exit 2 / `"decision": "deny"`).

### 3.3 Terminal Multiplexer Subsystem (`run_command`)
Shell execution within Antigravity 2.0 is handled through a persistent pseudo-terminal multiplexer:
- **Parameters**:
  - `CommandLine` (required): Command string executed via `bash -c`.
  - `Cwd` (required): Absolute path to working directory.
  - `RunPersistent` (boolean): When `true`, executes inside a persistent terminal shell instance that preserves shell environment variables across separate calls.
  - `RequestedTerminalID` (string): Reuses an established persistent terminal session.
  - `IsDaemon` (boolean): Flags long-running processes (development servers, watchers, tunnels) that are not expected to terminate autonomously.
  - `WaitMsBeforeAsync` (integer, max 10,000ms): Synchronous wait threshold. Commands terminating within this threshold return output immediately; commands exceeding it transition cleanly to background tasks.
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

### 3.6 Native Slash Commands, XML Prompt Wrappers & Invokable Subagent `TypeName`s

Antigravity intercepts **9 native system slash commands** client-side/server-side (`SLASH_COMMAND_TYPE_SYSTEM`), rewriting user prompts into dedicated XML wrapper directives or triggering stateful handlers (`PreInvocation` harness hooks bypass all native slash commands to avoid collisions):

| System Slash Command | Prompt Wrapper / Control Marker | Functional Semantics |
| :--- | :--- | :--- |
| **`/boost`** | `<ORCHESTRATOR>` | Dispatches two-tier deep reasoning / parallel swarm refinement (`owl` / `DeepCoder` / `DeepInvestigator` + anti-anchoring verification). |
| **`/teamwork-preview`** | `<TEAMWORK>` | Launches coordinated multi-agent patterns (SWE Light, DAG + Blackboard, Colosseum funnel, Document Review RSA; see [`cockpit-director.md`](cockpit-director.md)). |
| **`/plan`** | `<PLAN>` | Activates read-only planning modal loop (`implementation_plan.md` + interactive feedback gate). |
| **`/grill-me`** | `<GRILL_ME>` | Forces Socratic edge-case interrogation before committing to design or edits. |
| **`/goal`** | `<!-- GOAL_COMPLETE -->` / `<!-- GOAL_CANCELLED -->` | Bounded autonomous iteration loop; termination gated on explicit HTML comment sentinel markers. |
| **`/browser`** | `<SUBAGENT>` -> `browser` | Delegates visual/DOM/Playwright web tasks to the isolated `browser` subagent. |
| **`/schedule`** | `schedule` tool invocation | Creates one-shot timers or recurring 5-field cron jobs. |
| **`/learn`** | `<LEARN>` | Extracts reusable session conventions/patterns into skill or rule artifacts. |
| **`/compact`** | Engine checkpoint pass | Triggers manual context compaction and inserts a compaction checkpoint barrier (`enum 23`). |

**Hidden Invokable Subagent `TypeName`s**: Beyond workspace Markdown agents (`.agents/agents/*.md`), `invoke_subagent` recognizes **4 native internal `TypeName`s**:
1. **`DeepCoder`**: Runs `DeepCoderWorkerL0` + `DeepCoderImprovementWorker` for deep multi-file implementation/repair.
2. **`DeepInvestigator`**: Runs `DeepInvestigatorWorkerL0` + `DeepInvestigatorImprovementWorker` for forensic codebase diagnosis.
3. **`teamwork_preview`**: Exposes team workers (`orchestrator@colosseum`, `critic@colosseum`, `explorer@colosseum`, `implementer`, `qa`, `armed_worker@colosseum`).
4. **`browser`**: Isolated headless browser subagent for web interaction and UI verification.

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

The Lifecycle Hooks engine executes **deterministic code outside the model context window** via `hooks.json` or Python SDK callbacks (see [`lifecycle-hooks.md`](lifecycle-hooks.md) for wire schemas, layout duality, and the complete reference specification). `agyis-harness` registers **7 hook blocks** in `hooks.json` covering **8 verified hook runner checks** (`psl-stop-verification-fence` dispatches both `verification-fence` and `post-verification-fence`).

### 5.1 The Core Lifecycle Events (`hooks.json`)

| Event | Layout / Matcher Target | Execution Point | Expected `stdout` Output |
| :--- | :--- | :--- | :--- |
| **`PreToolUse`** | Matcher-grouped regex (`run_command`, `view_file\|grep_search`, `*`) | Before tool dispatch | `{"decision": "allow"\|"deny"\|"ask"\|"force_ask", "overwrite": {...}, "reason": "..."}` |
| **`PostToolUse`** | Matcher-grouped regex on tool name | Immediately after tool completion | **`{}`** (strictly empty JSON object, Exit `0`) |
| **`PreInvocation`** | Flat list (no matcher) | Before inference dispatch | `{"injectSteps": [...]}` (`ephemeralMessage` / `userMessage` string; `systemMessage` nested dict) |
| **`PostInvocation`** | Flat list (no matcher) | After inference generates tool calls | `{"injectSteps": [...], "terminationBehavior": "force_continue"\|"terminate"\|""}` |
| **`Stop`** | Flat list (no matcher) | Trajectory termination boundary | `{"decision": "continue", "reason": "..."}` or allow exit (9 `terminationReason` values; 2-block valve) |

### 5.2 JSON Protocol Highlights (camelCase Protojson over Stdio)

- **Common Ingress Metadata**: `conversationId`, `stepIdx` / `invocationNum` / `executionNum`, `workspacePaths`, `transcriptPath`, `artifactDirectoryPath`, `modelName`.
- **Shallow `overwrite` Semantics (`PreToolUse`)**: Replaces matching top-level argument keys in-flight (`CommandLine`) before dispatch and transcript capture.
- **`PreInvocation` Nested `systemMessage` Envelope**: Plain strings work for `{"ephemeralMessage": "..."}` and `{"userMessage": "..."}`, whereas `systemMessage` requires the nested envelope `{"systemMessage": {"systemMessage": "...", "metadata": {...}}}`.

---

## 6. Surface Deconstruction: Model Context Protocol (MCP) Boundaries

Antigravity integrates with the Model Context Protocol (MCP) to provide clean boundaries between the agent core and external tool providers.

### 6.1 Transports
1. **Stdio Transport (Local Process)**:
   - Language Server spawns the target executable directly and communicates over standard input/output using JSON-RPC (`command`, `args`, `env`).
2. **Streamable HTTP / SSE Transport (Remote Service)**:
   - Connects to remote MCP endpoints over HTTP using Server-Sent Events (`serverUrl`, `headers`).

### 6.2 Tool Filtering (Allowlist / Denylist)
To prevent tool schema explosion (`5` unfiltered MCP servers expose `283` tools totaling `263,759` schema tokens vs. `16` skills consuming only `1,330` inline tokens), MCP server configurations enforce strict tool filtering:
```python
stdio_server = types.McpStdioServer(
    name="remote_ops_service",
    command="python3",
    args=["-m", "remote_ops.mcp_server"],
    enabled_tools=["remote_node_status", "remote_exec"],  # Allowlist: ONLY these 2 tools exposed
    # disabled_tools=["dangerous_wipe"]                    # Denylist: Mutually exclusive filter
)
```

### 6.3 FastMCP Compliance & Boundary Invariants
- **Identifier Safety**: FastMCP requires all tool names and parameter keys to match `^[a-zA-Z_][a-zA-Z0-9_]*$`.
- **Synchronous Blocking Boundary**: MCP tool calls execute synchronously from the agent loop's perspective; long-running remote work should offload cleanly.
- **Safety Policy Binding**: Under strict deny-by-default policies (`policy.deny_all()`), explicitly permit required servers via `policy.allow(mcp_server)`.

---

## 7. Empirical Gap Analysis: Workstation Failures vs. Platform Capabilities

Audited telemetry baselines in [`../taxonomy/empirical-baselines.md`](../taxonomy/empirical-baselines.md) (`1,734` classified sessions / `389,329` steps / `178,747` tool calls / `4,132` (`2.31%`) tool errors / `3,008` (`1.73/sess`) interventions; live `2026-11-11` corpus: `2,875` sessions / `598,911` steps / `424,817` calls / `11,510` (`2.71%`) errors / `5,604` interventions) establish four foundational empirical dynamics (historical cohort breakdowns are archived in [`../archive/taxonomy/workstation-audit-report.md`](../archive/taxonomy/workstation-audit-report.md)):

1. **Tool Execution Succeeds Yet Sessions Still Stall**: Across `3,275` audited interventions (`operator_interventions_summary.json`), only `26` (`0.79%`) followed a failed tool call; `99.21%` followed technically succeeding tools due to drift, context bloat, polling inflation, or verification gaps.
2. **Session Burden Surges with Depth While Per-Call Precision Remains Flat**:
   - **Per-call error rate remains stable** (`1.87%–2.80%`: `1.87%` at `11–50` steps vs `2.70%` at `200+` steps; refuting older assumptions of a `20x–40x` per-call syntax/edit precision collapse).
   - **Cumulative session errors and interventions surge sharply** under depth and token saturation: `<20k` tokens averages `1.26` errors and `1.22` interventions/session vs `57.79` errors (**`45.9x`**) and `39.00` interventions (**`32.0x`**) at `200k+` tokens (`24.4x` errors and `14.0x` interventions at `200+` steps).
3. **Output Compaction & Progressive Skill Disclosure**: Bounded `2 KB` head/tail output compaction saves **`39.69%`** of output characters across `43,884` calls (`0` failure violations) and `21.31%` of session context (`<0.25 ms` runtime). Progressive skill loading (`1,330` inline tokens for `16` skills) outperforms eager MCP tool exposure (`263,759` schema tokens across `5` servers).
4. **Reasoning Effort Trade-off**: Heuristic trajectory grading (`reasoning_benchmark_results.json`) measured `46.8%` accuracy at `1,196.46s` (`gemini-3.8-flash-low`) vs `46.6%` at `47,287.14s` (`gemini-3.8-flash-high`) and `35.7%` at `1,162.47s` (`gemini-3.1-pro`).

### Gap Matrix: Empirical Failure Mode vs. Architectural Layer

| Empirical Failure Mode | Root Cause | Layer 1: Native Platform Feature | Layer 2: Lifecycle Hook (`hooks.json`) | Layer 3: Skills / CLI Tooling |
| :--- | :--- | :--- | :--- | :--- |
| **Exit Code 1 Search Probing** | Benign `grep` / `diff` exiting 1 on empty match treated as failure. | Native search tools (`grep_search`). | **`PreToolUse` (`command-safety`)**: Rewrites standalone probes via `overwrite` with `\|\| [ $? -eq 1 ]`. | Rule invariant (`PSL-INV-002`). |
| **Exit Code 127 Missing Binaries** | Non-login subshells missing user dotfiles / `.venv` Python. | `LocalAgentConfig(env=...)`. | **`PreToolUse` (`command-safety`)**: Injects user toolchain `PATH` shims + `uv` CPython >= 3.12 (`ADR-013`, `ADR-023`). | `agyis doctor --heal`. |
| **Remote SSH Hangouts (Exit 255)** | Unreachable remote targets hanging raw SSH commands. | Short-lived multiplexed transports. | **`PreToolUse` (`command-safety`)**: Injects `-o ConnectTimeout=5 -o BatchMode=yes` (`ADR-023`). | **`agyis remote` (`ADR-027`)** + `remote-ops` / `mesh-ops` skills. |
| **Interactive TUI Hangs** | Unpiped pagers or interactive editors (`vim`, `nano`, `less`). | Headless `--print` / `PAGER=cat`. | **`PreToolUse` (`command-safety`)**: Rewrites `PAGER=cat`, blocks interactive TUI binaries. | Non-interactive skill contracts. |
| **Redundant File / Search Loops** | Consecutive unchanged `view_file`, `grep_search`, or `run_command` loops. | Structured subagent delegation (`<40k` ctx). | **`PreToolUse` (`anti-loop`)**: Blocks repeat identical tool calls; allows evolved queries. | Zero-Exploration Invariant. |
| **Background Polling Inflation** | Polling async tasks or `.system_generated/{tasks,logs}/` files instead of stopping. | **Native Reactive Wakeup** (`<SYSTEM_MESSAGE>`). | **`PreToolUse` (`anti-loop`, Issue #41)**: Emits non-blocking **advisory allow** on `manage_task(Action='status')`; **Exit 2 deny** on repeated log-file polling. | Reactive Wait rule (`PSL-INV-004`, `ADR-032`). |
| **Long-Context Saturation & Flood** | Unbounded stdout dumps pushing sessions toward `200k+` tokens (`45.9x` error burden). | `CompactionConfig`, `/compact`, checkpoint barriers. | **`PostToolUse` (`compactor`)** `2 KB` truncation + **`PreToolUse` (`token-proximity`)** / **`PreInvocation` (`pre-invocation`)** advisories (`180k`/`230k`). | `agyis checkpoint` + fresh subagents. |
| **Premature Completion / Plan Drift** | Claiming done without tests or cleanroom spec verification, or mutating outside plan. | `/plan` mode + SDK review gates. | **`Stop` (`verification-fence`)** (`code_dirty` vs `spec_dirty`, 2-block valve) + **`PreToolUse` (`anti-drift`)**. | `agyis test` / `agyis verify --spec`. |

---

## 8. Three-Tier Architectural Boundaries & Recommendations for `agyis-harness`

1. **Tier 1 — Native Platform Primitives**:
   - Rely on native reactive task wakeups, native OS sandboxing, `CompactionConfig` / `/compact`, native `/plan` / `/boost` / `/teamwork-preview` workflows, and `enabled_tools` MCP allowlists.
2. **Tier 2 — Deterministic Lifecycle Hooks (`hooks.json`, `7` blocks / `8` checks)**:
   - `command_safety_hook.py`: Shallow `overwrite` normalization (`PAGER=cat`, `|| [ $? -eq 1 ]`, `uv` CPython injection, user `PATH` shims, SSH timeouts) and destructive blocks.
   - `anti_loop_hook.py`: Repeat call circuit breaker, Issue #41 non-blocking `manage_task(Action='status')` advisory allow, and Exit 2 log-polling deny.
   - `output_compactor_hook.py`: Deterministic **`2 KB`** output compactor (`<0.25 ms`).
   - `anti_drift_hook.py` & `completion_fence_hook.py`: Plan adherence, read-only auditor write fence, and decoupled `code_dirty` / `spec_dirty` stop gating.
   - `token_proximity_guard.py` & `pre_invocation_hook.py`: `180k`/`230k` runway gauges, role pinning, and `.agents/artifacts/compaction_checkpoint_latest.md` / `cockpit_checkpoint.md` succession.
3. **Tier 3 — Modular Skills, Agent Personas & Remote CLI**:
   - Package **30** progressive-disclosure skills (`<24,576 B` cap, `>100 L` ToC) and **8** dual-mode agent personas (`agyis_architect`, `agyis_coordinator`, `agyis_investigator`, `agyis_planner`, `agyis_builder`, `agyis_reviewer`, `agyis_custodian`, `agyis_auditor`).
   - Standardize remote execution through OpenSSH ControlMaster multiplexing via **`agyis remote`** (`ADR-027`) and `remote-ops` / `mesh-ops` skills, isolating network timeouts from context windows.

---

## 9. Definitive Platform Surface Comparison

| Feature / Dimension | Antigravity CLI (`agy`) | Antigravity 2.0 Desktop | Official Python SDK | Lifecycle Hooks (`hooks.json`) |
| :--- | :--- | :--- | :--- | :--- |
| **Primary Consumer** | Terminal developer, CI/CD, batch runners | GUI developer, pair programming | Services, custom agent harnesses, evaluators | Safety guards, linters, policy enforcement |
| **Execution Modality** | Interactive TUI, Batch `-p`, NDJSON stream | Visual Electron app, Connect RPC, Canvas | Programmatic async context manager | Synchronous hook subprocesses (stdio) |
| **Reasoning Control** | `--effort low\|medium\|high` | Global & Project Settings menu | Endpoint model options / budget configs | N/A (runs before/after inference) |
| **Tool Execution Safety** | `--dangerously-skip-permissions`, `--sandbox` | Global/Project Tool Policy (`strict`, `sandbox`) | 9-level declarative policy hierarchy (`policy.*`) | `PreToolUse` decision: `allow`, `deny`, `ask`, `force_ask` |
| **Tool Argument Modification** | Flags only | Flags / UI confirmation | SDK wrapper functions | **`PreToolUse` shallow `overwrite`** |
| **Context Management** | Native compaction | `/compact`, visual tabs, progressive artifacts | `CompactionConfig(token_threshold)` | `PostToolUse` `2 KB` compaction + `180k`/`230k` gauges |
| **Task Concurrency** | Background daemon (`remote-control`) | `manage_task` pane + reactive wakeup bus | `asyncio` event loop + custom tasks | Advisory allow on `manage_task`; deny `.system_generated/{tasks,logs}/` polling |
| **Completion Fencing** | Exit code / JSON schema validation | Interactive feedback gates (`/plan`) | Budget and stop hook delegates | **`Stop` hook `decision="continue"` (2-block valve)** |
