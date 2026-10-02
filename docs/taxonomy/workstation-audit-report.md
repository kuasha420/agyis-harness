# 📊 Workstation Empirical Telemetry & Audit Report
**Project**: PSL Harness for Google Antigravity™ (`psl-agy-harness`)  
**Publisher**: Purrfect Software Limited (PSL)  
**License**: Apache-2.0  
**Generated At**: 2026-10-02 04:40:39Z  
**Data Source**: Workstation telemetry mined from `~/.gemini/antigravity/brain/*/transcript.jsonl`

---

## Executive Summary

An exhaustive empirical audit of all developer sessions recorded on this primary development workstation was conducted using the `psl-agy-harness` telemetry harvester. 

| Metric | Empirical Value | Significance |
| :--- | :--- | :--- |
| **Total Sessions Audited** | **348** | Broad empirical baseline spanning multiple major engineering initiatives. |
| **Total Trajectory Steps** | **140,005** | Deep step-by-step telemetry covering planning, coding, and debugging. |
| **Total Tool Executions** | **64,065** | High volume of tool interactions across file systems, terminals, and MCP. |
| **Tool Failures Encountered** | **2,232** (3.48%) | Concrete failure states requiring either recovery or operator rescue. |
| **Human Operator Interventions** | **1,690** (4.86 / session) | Direct steering, confirmations, corrections, or rescue prompts. |
| **Repeated Tool Loop Calls** | **5,773** | Redundant tool thrashing consuming context and latency. |

---

## 🔬 The Empirical Taxonomy: 4 Operational Buckets

### 🟢 1. WHAT WORKED (High-Fidelity Autonomous Trajectories)
- **High Autonomous Convergence in Short-to-Medium Trajectories (11–50 steps)**:
  - 69 sessions completed with an average of **0.3 tool errors** and **0.0 operator interventions**.
  - Single-turn code edits via `replace_file_content` achieved a **99.9% success rate** (only 4 failures out of 4,650 calls).
- **Subagent Delegation Stability**:
  - `invoke_subagent` (203 calls) and `manage_subagents` exhibited a **99.5% success rate**, demonstrating that subagent lifecycle management is structurally solid when properly scoped.
- **MCP Tool Precision**:
  - `call_mcp_tool` achieved a **98.6% success rate** across 147 calls, verifying that standard MCP stdio tool dispatching operates reliably once configured.

---

### 🔴 2. WHAT FAILED (Mechanistic & Operational Breakdowns)

#### Top Failing Tools Breakdown
| Tool Name | Total Calls | Failures | Failure Rate (%) | Primary Failure Mode |
| :--- | :--- | :--- | :--- | :--- |
| `run_command` | 28,348 | 2,196 | 7.75% | Exit code != 0, command not found, SSH timeout |
| `grep_search` | 3,375 | 14 | 0.41% | Syntax / pattern mismatch |
| `manage_task` | 2,703 | 5 | 0.18% | Task ID invalid or expired |
| `list_dir` | 1,108 | 4 | 0.36% | Schema / target error |
| `replace_file_content` | 4,650 | 4 | 0.09% | Schema / target error |
| `view_file` | 18,096 | 4 | 0.02% | Schema / target error |
| `call_mcp_tool` | 147 | 2 | 1.36% | Schema / target error |
| `define_subagent` | 12 | 1 | 8.33% | Schema / target error |

#### Exit Code Distribution for `run_command` (2,192 Total Failures)
The terminal tool (`run_command`) is responsible for **98.4% of all tool failures** across the workstation.
- **Exit Code 1** (1,544 occurrences): General error (test failure, git diff grep non-zero, process failure)
- **Exit Code 2** (245 occurrences): Misuse of shell built-ins or CLI syntax
- **Exit Code 127** (143 occurrences): Command not found (`PATH` issues, uninstalled binary)
- **Exit Code 255** (72 occurrences): SSH / remote node connection failure or remote host unreachable
- **Exit Code 128** (52 occurrences): Invalid git argument / fatal repository error
- **Exit Code 3** (31 occurrences): Process exit code 3
- **Exit Code 8** (16 occurrences): Process exit code 8

#### Tool Thrashing & Loop Traps (5,773 Occurrences)
Redundant consecutive tool calls on identical arguments:
- **`view_file`**: **3,951 repeated calls**. Agents re-reading files without state caching or paging awareness.
- **`grep_search`**: **625 repeated calls**. Repeated pattern search attempts without broadening or altering queries.
- **`manage_task`**: **300 repeated calls**. Runaway polling loops instead of reactive timer/task waiting.
- **`run_command`**: **360 repeated calls**. Repeatedly re-running the same failing command.

#### The Context Cliff: Trajectory Length vs Error Escalation
- **1-10 steps** (4 sessions): Avg Errors = **0.25**, Avg Operator Interventions = **0.25**
- **11-50 steps** (69 sessions): Avg Errors = **0.35**, Avg Operator Interventions = **0.04**
- **51-200 steps** (176 sessions): Avg Errors = **0.99**, Avg Operator Interventions = **0.4**
- **200+ steps** (99 sessions): Avg Errors = **20.54**, Avg Operator Interventions = **16.32**

> [!CAUTION]
> **The 200+ Step Cliff**: When session trajectories exceed 200 steps, the average tool error rate jumps **20x** (from 1.0 to 20.5), and human operator interventions jump **40x** (from 0.4 to 16.3). Unpruned tool outputs and compounding errors cause severe context degradation.

---

### 🟡 3. OPERATOR GUIDANCE (Human-in-the-Loop Interventions)

Across 348 sessions, human operators stepped in **1,690 times**:
- **`OPERATOR_GUIDANCE`**: **1,054** occurrences (62.4%)
- **`CONFIRMATION`**: **261** occurrences (15.4%)
- **`CONTINUATION`**: **128** occurrences (7.6%)
- **`STEERING`**: **127** occurrences (7.5%)
- **`CREDENTIALS`**: **98** occurrences (5.8%)
- **`ERROR_RECOVERY`**: **22** occurrences (1.3%)

#### Core Steering Triggers Observed
1. **Stop & Hold Fences (69 occurrences)**: Operator explicitly commanding agent to halt runaway execution or pause before making risky destructive mutations.
2. **Trajectory Drift Redirection (4 occurrences)**: Operator correcting the agent after it deviated from the agreed implementation plan (`"Oh no you drifted - what was the initial plan I shared?"`).
3. **Mesh & Hardware Orchestration (13 occurrences)**: Directing actions across remote Knot mesh nodes (Desktop Anchor, Laptop CUDA, ROG Ally, Steam Deck) where agent attempted local commands or failed SSH calls (`"Wait we need to onboard the new account in steam deck from desktop"`).
4. **Credential & Secret Provisioning (98 occurrences)**: Supplying passwords, API keys, and environment tokens that cannot be checked into VCS.
5. **Architectural & Design Plan Approvals (261 occurrences)**: Confirming implementation plans and verifying safety fences before proceeding.

---

### 🚀 4. HARNESS OPPORTUNITIES (Actionable Solutions for `psl-agy-harness`)

Based on empirical workstation telemetry, `psl-agy-harness` must implement the following reference components:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        psl-agy-harness Reference                       │
├────────────────────────────┬────────────────────────────┬──────────────┤
│       Lifecycle Hooks      │       Telemetry Rules      │  Mesh Skills │
├────────────────────────────┼────────────────────────────┼──────────────┤
│ • PreToolUse Anti-Loop     │ • Anti-Loop Heuristics     │ • Knot Node  │
│ • PreToolUse Command Check │ • Error-Recovery Fences    │   Orchestr.  │
│ • PostToolUse Output Prune │ • Context Conservation     │ • Tuplespace │
│ • Stop / Gate Checklist    │ • Zero-Token Mesh Protocol │   Client     │
└────────────────────────────┴────────────────────────────┴──────────────┘
```

1. **`PreToolUse` Anti-Loop Guard**:
   - Intercept identical consecutive calls to `view_file` or `grep_search`.
   - Inject cached result or synthetic redirection error to break loops before context is wasted.
2. **`PreToolUse` Pre-flight Command Validator**:
   - Check if command binaries exist before executing (mitigating Exit Code 127).
   - Normalize commands that return non-zero for empty matches (e.g. `grep -E '...' || true`).
3. **`PostToolUse` Output Truncator**:
   - Automatically compress tool outputs exceeding 2KB into semantic summaries, eliminating the 200+ step context cliff.
4. **Hardware Mesh Remote Execution Wrapper**:
   - Wrap SSH commands (`exit code 255`) with network liveness checks and fallback protocols.
5. **Project-Level `AGENTS.md` Rules**:
   - Codify anti-loop directives, proactive clarifying gates, and safe terminal guidelines directly in `.agents/rules/AGENTS.md`.

---

## Conclusion
This empirical baseline proves that the core Gemini reasoning capabilities are robust, but agent autonomy degrades primarily due to terminal tool friction (`run_command`), unmanaged tool loops (`view_file`), and unpruned context accumulation over long trajectories. 

The `psl-agy-harness` project will now systematically address each of these empirical failure modes using official Antigravity extension surfaces.
