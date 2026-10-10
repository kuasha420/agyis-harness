<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Purrfect Software Limited (PSL) -->

# 🧠 Cognitive Failure Taxonomy & Trace Deep-Dive (Tier 2)
**Project**: PSL Harness for Google Antigravity™ (`psl-agy-harness`)  
**Specification**: Horizon 1 — Tier 2 Qualitative Cognitive Forensics  
**Generated At**: 2026-10-02 05:17:00Z  
**Data Source**: 14,476 thinking traces (9,952,487 characters / ~2.49M tokens) from `~/.gemini/antigravity/brain/*/transcript.jsonl` correlated with `data/telemetry.db` across 348 developer sessions.

---

## 1. Executive Summary: What Happens Inside the Model's Reasoning?

While quantitative telemetry (exit codes, step counts, tool error counts) records **what** failed, Chain-of-Thought (CoT) thinking traces reveal **why** the model failed. An analysis of 14,476 thinking steps across 348 real-world developer sessions demonstrates that agent breakdowns are rarely random. Instead, they follow predictable cognitive failure dynamics rooted in context saturation, misaligned exit code interpretation, and attention sink collapse.

### Core Discoveries:
1. **The Awareness-Action Disconnect**: The model frequently acknowledges in its internal thinking that a command or action failed (e.g., *"The command failed with exit code 1"*), yet in the very next turn generates the identical tool invocation or a superficial variant without altering the underlying failure condition (**The Repetition Trap**).
2. **The Zero-Match Misdiagnosis**: `grep`, `git grep`, and `diff` return Exit Code 1 when zero matches are found. The model frequently misinterprets this benign negative search result as a fatal process crash or evidence of an imaginary codebase defect (**The Exit Code 1 Panic**).
3. **Unverified Environmental Presumptions**: The model routinely hallucinates CLI flags (`agy login --no-browser`), commands (`grim`, `deskflow-server`, `turbo`), and paths without executing pre-flight verification (`which` / `command -v`), directly driving 143 Exit Code 127 crashes (**The Hallucinated Environment**).
4. **Attention Sink Collapse & Semantic Perseveration**: Under extreme context load (>1,000 steps, >200k tokens), the model's internal Chain-of-Thought experiences cognitive degeneration. In session `8d6608ca` (10,717 steps), **85.5% (1,829 steps)** of all thinking traces perseverated on the exact same generic mantra (*"Prioritizing Tool Usage..."*), while the agent committed commits to the wrong branch, triggered 281 errors, and necessitated 201 human interventions (**The Disorientation Spiral**).
5. **Decoupled False Rationalization**: When faced with assertion errors, permission blocks, or network timeouts, the model's thinking trace frequently rationalizes that the negative output was *"expected"*, *"benign"*, or *"confirms expected functionality"*, proceeding to mutate codebase state on false premises (**The False Rationalization**).

---

## 2. Empirical Cognitive Failure Modes Taxonomy

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             PSL Empirical Cognitive Failure Modes                                │
├──────────────────────────┬─────────────────────────────────┬─────────────────────────────────────┤
│ Cognitive Failure Mode   │ Primary Manifestation           │ Core Driving Mechanism              │
├──────────────────────────┼─────────────────────────────────┼─────────────────────────────────────┤
│ 1. The Repetition Trap   │ Identical tool calls repeated   │ Cognitive inertia; lack of backoff; │
│                          │ 2–92x despite acknowledged fail │ manual polling instead of reactive  │
├──────────────────────────┼─────────────────────────────────┼─────────────────────────────────────┤
│ 2. Hallucinated Env.     │ Unverified tools/flags/paths    │ Speculative execution; missing      │
│                          │ causing Exit 127 & Exit 2       │ pre-flight check invariants         │
├──────────────────────────┼─────────────────────────────────┼─────────────────────────────────────┤
│ 3. Disorientation Spiral │ Lost branch/path state; memory  │ 100k+ token saturation; attention   │
│                          │ erasure; semantic perseveration │ sink collapse; context cliff        │
├──────────────────────────┼─────────────────────────────────┼─────────────────────────────────────┤
│ 4. False Rationalization │ Real errors dismissed as benign │ Cognitive dissonance avoidance;     │
│                          │ or "working as expected"        │ superficial output inspection       │
├──────────────────────────┼─────────────────────────────────┼─────────────────────────────────────┤
│ 5. Exit Code 1 Panic     │ Zero matches on grep/diff       │ Posix status code conflation;       │
│                          │ treated as runtime crash/defect │ failure to expect clean return 1    │
└──────────────────────────┴─────────────────────────────────┴─────────────────────────────────────┘
```

---

## 3. Deep-Dive: Mode 1 — The Repetition Trap

### Definition
The agent recognizes that a tool call did not succeed, or that a process is running asynchronously, yet it repeatedly executes the identical tool call (or a trivial directory shift) without modifying parameters or awaiting system notifications. Across the workstation corpus, **5,773 loop candidate tool calls** were recorded, including **3,951 repeated `view_file` calls**, **625 repeated `grep_search` calls**, and **360 repeated `run_command` calls**.

### Cognitive Etiology
1. **Manual Polling vs. Reactive Wakeup**: When initiating background tasks or long builds, the model fails to surrender control to the reactive event loop. Instead, it enters a tight manual polling cycle, reading task log files every 3 seconds.
2. **Directory Shuffling instead of Dependency Resolution**: When a script fails due to a missing dependency (e.g. `Cannot find module 'axios'`), the model rationalizes that the module might be located in a sibling folder, executing the exact same command across 4 different working directories before addressing the root cause.
3. **Loss of File State Retention**: As earlier file read outputs slide out of the immediate context window or get compressed, the model repeatedly re-reads identical files (e.g. `hub.py` re-read 92 times in `9499fee6`).

### Forensic Trace Case Studies

#### Case 1A: The Missing Module Directory Shuffle (`8d6608ca`, Steps 3230–3239)
*Context*: In workspace `mm-website`, the agent generated a scratch script `list_projects.js` requiring `axios`.
```text
Step 3230 [write_to_file]: Creates scratch/list_projects.js requiring 'axios'
Step 3231 [run_command] Cwd: /workspace
     ↳ Exit Code 1: "Error: Cannot find module 'axios'"
Step 3233 [run_command] Cwd: /workspace/mm-website
     ↳ Exit Code 1: "Error: Cannot find module 'axios'"
Step 3235 [run_command] Cwd: /workspace/purrmission/apps/pawthy
     ↳ Exit Code 1: "Error: Cannot find module 'axios'"
Step 3237 [run_command] Cwd: /workspace/purrmission
     ↳ Exit Code 1: "Error: Cannot find module 'axios'"
Step 3239 [write_to_file]: Finally rewrites list_projects.js to use native fetch()!
```
*Thinking Trace Analysis*:
> The model's thinking recognized in Step 3232 that `axios` was missing, but rationalized that running the command inside `mm-website workspace where axios is available` would resolve it. When that failed, it rationalized running it in `pawthy`, and then in `purrmission root`. It took **4 consecutive failures and ~800 tokens of redundant error traces** before the agent realized native `fetch()` required zero external dependencies.

#### Case 1B: Runaway Task Log Polling (`39a982aa`, Steps 391–455)
*Context*: A background build `task-388` was running.
```text
Step 391 [view_file]: ~/.../tasks/task-388.log (lines 1-800)
Step 393 [view_file]: ~/.../tasks/task-388.log (lines 1-800)
Step 395 [view_file]: ~/.../tasks/task-388.log (lines 1-800)
... [Repeated 32 times across 64 steps] ...
Step 397 [SYSTEM CHECKPOINT]: Context truncated due to length!
Step 398-454: Model continues re-reading task-388.log every 3 seconds!
Step 456 [SYSTEM_MESSAGE]: [Message] task-388 finished.
```
*Thinking Trace Analysis*:
> The model did not yield turn execution to await the reactive wakeup message. Instead, it burned 32 consecutive tool calls polling a static log file, directly triggering a mid-session context checkpoint truncation.

---

## 4. Deep-Dive: Mode 2 — The Hallucinated Environment

### Definition
The model's Chain-of-Thought generates plans based on assumed system utilities, CLI subcommands, or file paths that have not been verified in the current environment. This drives **143 Exit Code 127 (`command not found`)** errors and **245 Exit Code 2 (syntax/argument error)** failures.

### Cognitive Etiology
1. **Speculative CLI Synthesis**: The model assumes that because a tool is named `agy`, it must possess an `agy login --no-browser` subcommand analogous to `gh auth login`.
2. **PATH & Environment Non-Uniformity**: The model assumes that binaries available on one workstation node (`desktop`) are present across remote mesh strands (`laptop`, `steamdeck`), or assumes global package installations (`turbo`, `vitest`) instead of repo-local binaries (`./node_modules/.bin/turbo`).

### Forensic Trace Case Studies

#### Case 2A: The Speculative Subcommand (`efa95f0e`, Step 3038–3040)
*Context*: Authenticating Antigravity on a headless knot strand.
*Tool Call (Step 3038)*: `agy login --no-browser`  
*Outcome (Step 3039)*:
```text
The command exited with code 2.
Output: Error: unexpected argument "login". Prompts are read only from -p/--print, -i/...
```
*Direct Thinking Trace (Step 3040)*:
> *"The initial attempt to log in using a specific command failed, indicating an unexpected argument. The failure would have been catastrophic without a defensive mechanism. The question then becomes, what is the correct way to disable the browser? Investigation reveals the use of an environment variable setting within a configuration script: `BROWSER=/bin/true`. This suggests that setting this environment variable might be the solution..."*

*Forensic Analysis*: The model hallucinated both the subcommand `login` and the flag `--no-browser`. Rather than checking `agy --help`, it assumed a conventional OAuth CLI structure, failed with Exit Code 2, and then pivoted to manipulating desktop environment variables.

#### Case 2B: Remote Strand Binary Hallucination (`4ecaf914`, Step 6870)
*Context*: Automated cockpit screenshot capture across the Knot mesh.
*Direct Thinking Trace (Step 6870)*:
> *"Initial monitoring begins. Will capture the screen every 30 seconds, analyzing for any changes in state. Protocol dictates escalating to more detailed capture only if the initial scan indicates a significant event or anomaly."*
*Tool Call*: `grim ~/.gemini/antigravity/brain/4ecaf914.../cockpit_scan_8.png`  
*Outcome*:
```text
The command exited with code 127.
Output: bash: line 1: grim: command not found
```
*Forensic Analysis*: The model assumed Wayland utility `grim` was installed globally without executing `command -v grim` or checking the KDE desktop environment tools (`spectacle`).

---

## 5. Deep-Dive: Mode 3 — The Disorientation Spiral

### Definition
As session depth crosses the **200+ step / 100k token Context Cliff**, unpruned tool outputs saturate the sliding context window. The agent loses track of current branch states, repository boundaries, and agreed implementation plans, leading to acute disorientation and **Semantic Perseveration**.

### Cognitive Etiology: Attention Sink Collapse
Under heavy context load, the attention weights of transformer models can collapse into repetitive attractors ("attention sinks"). Rather than dynamically synthesizing thoughts based on the immediate turn, the model repeatedly outputs an internalized reasoning prefix (a "perseverated mantra").

### Forensic Trace Case Studies

#### Case 3A: Massive Semantic Perseveration (`8d6608ca`, 10,717 steps)
*Context*: A complex deployment and infrastructure refactor in `mm-website` and `purrfectcore`.
*Quantitative Finding*:
- **Total Thinking Steps**: 2,138
- **Perseverated Mantra Steps**: **1,829 steps (85.5%)**!
*The Perseverated Mantra*:
> *"**Prioritizing Tool Usage** I'm now focusing on tool selection, emphasizing specific tools over general ones where possible. The goal is to optimize efficiency by leveraging tools tailored to particular tasks, like viewing files. This strategy promises a more targeted and less error-prone approach..."*

*Impact on Agent Behavior*:
Because 85.5% of reasoning capacity was consumed by regurgitating this fixed paragraph, the agent experienced severe situational blindness:
1. **Step 6451**: The agent executed `git commit -m "Merge branch 'develop' into main..." && git cherry-pick dev && git push` directly to the `dev` branch.
2. **Step 6453 [Operator Alarm]**:
   > *"HIGH PRIORITY NOTICE!!! By the way, you accidentally commited the bycrypt restoration fix to purrfectcore-001/dev instead of `develop`. Yikes!!!"*
3. **Step 10056 [Operator Resign]**:
   > *"@[deployment_pipelines_refresher.md] in case you've forgotten everything again."*
4. **Step 10265 [Operator Intervention]**:
   > *"You didn't fast forward the deploy branch - there are commit diffs across develop and deploy - although they-re just marge commits. production is cleanfly fast forwarded. Can you investigate?"*

---

## 6. Deep-Dive: Mode 4 — The False Rationalization

### Definition
When tool executions return unexpected errors, non-zero exit codes, or assertion failures, the model engages in defensive rationalization—falsely asserting that the failure is expected, benign, or evidence of success, thereby bypassing error recovery protocols.

### Forensic Trace Case Studies

#### Case 4A: Decoupled Success Rationalization (`efa95f0e`, Step 3500)
*Context*: Verifying clipboard utilities on a remote node.
*Tool Call (Step 3500)*: `ssh laptop "which wl-copy xclip xsel"`  
*Outcome*:
```text
The command exited with code 1.
Output: [none - no utility found in PATH]
```
*Direct Thinking Trace (Step 3500)*:
> *"The command listing connected devices confirms the 'devbox' device is present and associated with a unique identifier. This suggests basic device discovery and pairing functionality is working as expected on the target system. This provides a baseline..."*

*Forensic Analysis*: The model's reasoning completely decoupled from the tool execution output! The tool failed to find any clipboard utility (code 1), yet the thinking trace hallucinated that the command confirmed connected devices and that device pairing was working as expected!

#### Case 4B: Rationalizing Test Assertion Failures (`761bb75c`, Step 688)
*Context*: Vitest suite testing localized Bengali date strings in `apps/api/src/lib/relative-date.test.ts`.
*Tool Call (Step 688)*: `pnpm exec vitest run apps/api/src/lib/relative-date.test.ts`  
*Outcome*: Exit Code 1 (Assertion Failed: received different date string).
*Direct Thinking Trace (Step 688)*:
> *"The code uses the Bengali locale ('bn') to format relative dates, and confirmed through multiple tests, the expected output for 'an hour ago' is indeed '১ ঘণ্টা আগে'. This is consistent across different tests and code locations."*

*Forensic Analysis*: Rather than reading the Vitest diff to identify why the assertion failed, the model used internal reasoning to rationalize that the existing code was undeniably correct, ignoring the test failure.

---

## 7. Deep-Dive: Mode 5 — The Exit Code 1 Panic

### Definition
The model equates any non-zero exit code with a catastrophic system failure. When utilities like `grep`, `git grep`, `diff`, or `test` exit with code `1` (indicating zero pattern matches or differences found), the model enters a state of confusion, hallucinating bugs or thrashing alternative queries.

### Forensic Trace Case Studies

#### Case 5A: Hallucinating Defects from Clean Grep (`1131ef45`, Step 78)
*Context*: Verifying that legacy paths do not exist in test suites.
*Tool Call (Step 78)*: `git grep -i -E "~/Dev/knot([^-_]|$)"`  
*Outcome*:
```text
The command exited with code 1.
Stdout: 
Stderr: 
```
*(Exit code 1 simply means zero matches were found—the codebase was clean!)*

*Direct Thinking Trace (Step 78)*:
> *"The `grep` results show a path normalization issue within the test suite. Specifically, the test expects a particular path for `port_out` that is likely not being set correctly by the `knot_path_normalize` function. This points to a potential mismatch or misconfiguration related to how the paths are handled during the test execution."*

*Forensic Analysis*:
This is a pure cognitive failure. The tool returned nothing because no matches existed. The model observed Exit Code 1, concluded that an error had occurred, and fabricated a detailed, false narrative about a "path normalization issue with `port_out`"!

#### Case 5B: CORS Origin Confusion (`8d6608ca`, Step 4454)
*Context*: Inspecting production environment variables for CORS configuration.
*Tool Call*: Grep for `CORS_ORIGIN` in remote env.  
*Outcome*: Exit Code 1.  
*Direct Thinking Trace (Step 4454)*:
> *"I've confirmed that `grep` returned an exit code 1, indicating `CORS_ORIGIN` is absent from production environment variables on Pawthy. I've also verified its critical nature; it's used in `main.ts` line 42, with a warning indicating the system fails closed if it's not present."*

*Forensic Analysis*: In this instance, the model correctly identified that the variable was absent, but treated the missing line as a fatal system stoppage rather than checking default fallback configurations.

---

## 8. Forensic Telemetry & Marker Distribution

Across the audited dataset, cognitive markers directly correlate with trajectory degradation:

| Cognitive Failure Marker | Trajectory Count | Avg Steps to Failure | Dominant Tool Involved | Primary Human Rescue Trigger |
| :--- | :--- | :--- | :--- | :--- |
| **Repetition Trap** | **49** | 185.4 | `view_file`, `manage_task` | Halt Fence (`"Stop!"`, `"Wait"`) |
| **Hallucinated Environment** | **3** (explicit) / 143 (code 127) | 42.1 | `run_command` | Steering (`"Tool is not installed"`) |
| **Disorientation Spiral** | **67** | 641.9 | `replace_file_content`, `git` | Drift Warning (`"You committed to wrong branch"`) |
| **False Rationalization** | **5** (explicit) / 53 (CoT) | 312.0 | `run_command` (tests) | Error Correction (`"That test is actually failing"`) |
| **Exit Code 1 Panic** | **30** (grep/diff) | 88.5 | `run_command` (`grep`) | Guidance (`"Grep returning 1 means no match"`) |

### Context Depth vs Error Escalation Curve

```text
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                        Session Trajectory Depth vs Failure Rates                      │
├────────────────────┬──────────┬───────────┬─────────────┬─────────────┬───────────────┤
│ Step Depth Tier    │ Sessions │ Avg Steps │ Avg Errors  │ Avg Interv  │ Severity      │
├────────────────────┼──────────┼───────────┼─────────────┼─────────────┼───────────────┤
│ Low (<50 steps)    │       72 |      24.6 |        0.33 |        0.06 | Minimal       │
│ Med (50-200 steps) │      177 |     106.8 |        0.99 |        0.40 | Controlled    │
│ High (200-1000)    │       69 |     412.5 |        7.84 |        6.81 | Elevated (8x) │
│ Extreme (1000+)    │       30 |    3285.0 |       49.73 |       38.20 | Critical(50x) │
└────────────────────┴──────────┴───────────┴─────────────┴─────────────┴───────────────┘
```

---

## 9. Concrete Harness Mitigation Specifications

To insulate Google Antigravity agents against these five empirical cognitive failure modes, `psl-agy-harness` must introduce mechanical lifecycle hooks and strict prompt invariants.

### A. PreToolUse Interventions

#### 1. `AntiLoopGuardHook`
* **Trigger**: PreToolUse on all tools (`view_file`, `grep_search`, `run_command`, `manage_task`).
* **Logic**:
  - Compute a deterministic hash of `(tool_name, arguments)`.
  - Maintain a sliding window buffer of the last 5 tool signatures.
  - If identical signature count $\ge 2$:
    - For `view_file` / `grep_search`: Intercept execution and return cached result with high-priority warning:  
      `[HARNESS INTERVENTION]: Redundant call detected. The content of this target is already present in your context history. Do not repeat identical queries.`
    - For `manage_task`: Intercept execution and enforce reactive pause:  
      `[HARNESS INTERVENTION]: Background task is active. Antigravity notifies you reactively on completion. Cease polling and yield turn.`

#### 2. `PreflightCommandValidatorHook`
* **Trigger**: PreToolUse on `run_command`.
* **Logic**:
  - Extract the root command binary from the command string.
  - Check against an in-memory cache of verified binaries.
  - If unverified, issue a silent, non-interactive `command -v <binary>` pre-check.
  - If binary does not exist: Fail fast before shell execution with synthetic error:  
    `[HARNESS PRE-FLIGHT ERROR]: Binary '<binary>' not found in PATH. Verify installation or use local path (e.g. ./node_modules/.bin/<binary>).`

#### 3. `BranchStateGuardHook`
* **Trigger**: PreToolUse on `run_command` when command contains `git commit`, `git push`, or `git merge`.
* **Logic**:
  - Compare current `HEAD` branch (`git rev-parse --abbrev-ref HEAD`) against target branch in task plan.
  - If agent is attempting to push/commit to a protected branch (`main`, `master`, `production`) or a misaligned branch (e.g., `dev` instead of `develop`), intercept and require explicit operator confirmation.

---

### B. PostToolUse Interventions

#### 1. `ExitCode1SanitizerHook`
* **Trigger**: PostToolUse on `run_command`.
* **Logic**:
  - Inspect if the executed command contains pattern matching utilities (`grep`, `git grep`, `diff`, `git diff`).
  - If process exited with `code == 1` and `stderr` is empty:
    - Rewrite status to `SUCCESS`.
    - Append explicit explanatory text to output payload:  
      `[Pattern Search Notice: Exit code 1 indicates 0 matches found. This is a clean search result, not an execution failure.]`
  - Eliminates 100% of Exit Code 1 Panic loops.

#### 2. `OutputCompactorHook` (The 2KB Ceiling)
* **Trigger**: PostToolUse on `run_command` and `view_file`.
* **Logic**:
  - Truncate any stdout exceeding 2,048 characters (preserving the first 500 chars and last 1,000 chars, plus exit code).
  - Eliminates 21.29% (~6.9M tokens) of context bloat, preventing sessions from entering the 200k+ token Attention Sink Collapse zone.

---

### C. Prompt Invariants for `AGENTS.md`

Add the following empirical rules to `.agents/rules/AGENTS.md`:

```markdown
## Empirical Cognitive Failure Defense Invariants

1. **The Grep Exit Code Invariant**:
   - `grep` and `diff` return Exit Code 1 when zero matches occur. 
   - Never interpret Exit Code 1 on pattern searches as an error, crash, or codebase defect. Treat it as: "0 occurrences found".

2. **The Reactive Wakeup Invariant**:
   - When a command or task is sent to the background (`manage_task` or long runner), NEVER execute repeated `view_file` calls on task log files.
   - Stop calling tools immediately. Await the system's reactive wakeup message.

3. **Pre-flight Tool Verification Invariant**:
   - Before executing non-standard binaries (`grim`, `turbo`, `vitest`, `secret-tool`), verify presence via `command -v <bin>` or inspect `./node_modules/.bin/`.
   - Never assume flags exist on subcommands without verifying via `--help`.

4. **Negative Evidence Verification**:
   - If a test or command returns an error or non-zero exit code, do NOT rationalize that the error is "expected" or "benign" unless explicitly documented in task requirements.
   - Read the exact assertion failure diff before proceeding.
```

---

## 10. Conclusion & Architectural Roadmap

The empirical analysis of 14,476 thinking traces proves that cognitive failure in autonomous developer agents is predictable and systematic. The transition from unconstrained agent execution to the **PSL Harness** replaces fragile model self-monitoring with deterministic architectural safeguards.

By implementing `AntiLoopGuard`, `PreflightCommandValidator`, and `ExitCode1Sanitizer` in Horizon 2, `psl-agy-harness` will eliminate the root causes of the Repetition Trap, Hallucinated Environment, and Exit Code 1 Panic, keeping agents operating within their high-fidelity cognitive zone.
