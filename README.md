<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Purrfect Software Limited (PSL) -->

# PSL Harness for Google Antigravity™ (`psl-agy-harness`)

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Platform](https://img.shields.io/badge/Platform-Google_Antigravity-4285F4.svg)](https://antigravity.google)
[![Status](https://img.shields.io/badge/Status-Active_Development_(Research_&_POC)-orange.svg)]()
[![Tests](https://img.shields.io/badge/Tests-401%2F401_Passing_(100%25)-brightgreen.svg)]()

> An open-source empirical audit pipeline and reference extension harness for **Google Antigravity™** by **Purrfect Software Limited (PSL)** under the **Apache-2.0** license.

---

> [!NOTE]
> **Project State Notice**: This repository has completed empirical ingestion of **722 real-world developer sessions (219,292 steps, 160,226 tool calls)**, verified isolated lifecycle hooks, codified hermetic testing contracts (401 passing tests in <1.0s), and packaged the unified 13-command `psl` developer CLI suite. See [roadmap.md](roadmap.md) for the master vision and upcoming milestones.

---

## 🎯 North Star & PSL Motivation

Google's Gemini models—with **Gemini 3.8 Flash** as our primary high-throughput SWE workhorse and **Gemini 3.1 Pro** as our deep architectural reasoning model—demonstrate market-leading long-context reasoning, tool fidelity, and price-to-performance efficiency for software engineering automation. However, developer productivity in long-horizon coding tasks is frequently constrained by harness-level friction:

1. **Context Cliffs & Output Flooding**: Unpruned tool outputs dump thousands of lines into context, accelerating the 100k-token cognitive degradation cliff.
2. **Terminal Desyncs & False-Positive Failures**: 98.4% of all tool failures occur in `run_command`, driven by benign exit code 1 panics (grep/diff), pyenv/conda shim hijacking, and interactive subshell hangs.
3. **Premature Convergence & Cognitive Drift**: In deep sessions (>100k tokens), models succumb to "chatbot seduction", confusing speculative text proposals with working code, rationalizing incomplete work, and perseverating on repetitive thought mantras.
4. **Environment Version Mismatch**: Models trained on modern syntax (e.g. Python >= 3.12 PEP 701 f-strings) crash when host workstations run outdated pyenv shims (Python 3.10), wasting context on syntax retries.

### Our Strategy: Build On, Not Against, Official Interfaces
Rather than creating an isolated, competing framework that reinvents agent execution, `psl-agy-harness`:
- **Audits Reality**: Ingests hundreds of local developer sessions (`~/.gemini/antigravity/brain/*/transcript.jsonl`) to construct an empirical taxonomy of real failure modes, loop states, and human operator interventions.
- **Dissects Official Surfaces**: Deeply analyzes the official `google-antigravity` Python SDK, `agy` CLI, plugin manifests, lifecycle hooks (`PreToolUse`, `PostToolUse`, `PreInvocation`, `PostInvocation`, `Stop`), and MCP servers.
- **Solves Friction in Code, Not Prompts**: Transparently guarantees certified runtimes and sanitized shell execution in deterministic lifecycle hooks, freeing prompt tokens for actual task reasoning.
- **Strict Contract Adherence**: Delivers all patterns strictly within official Antigravity plugin contracts, lifecycle hooks, and MCP interfaces for seamless compatibility.

---

## 📊 Ground Truth: Workstation Empirical Telemetry

From our automated audit of **722 developer sessions** (`data/telemetry.db`):

| Metric | Empirical Baseline | Key Takeaway |
| :--- | :--- | :--- |
| **Total Trajectory Steps** | 219,292 steps | Comprehensive long-horizon multi-project corpus. |
| **Total Tool Executions** | 160,226 tool calls | 97.46% success rate (4,062 tool errors, 2.54% error rate). |
| **Human Operator Interventions** | 2,738 interventions | Average 1.25 interventions / 100 steps (99.3% due to cognitive drift). |
| **Loop & Thrashing Traps** | 15,562 calls (9.71%) | Intercepted by deterministic Anti-Loop hook. |
| **Surgical Contiguous Edits** | 11,279 calls (99.47%) | ADR-013 validated: only 60 edit errors in 11k operations. |
| **The Context Cliff** | 5.2x error spike | Sessions exceeding 100k tokens suffer rapid error escalation. |
| **Context Bloat Elimination** | **21.3% token reduction** | Capping non-error outputs at 2KB saves >10M tokens. |

## 🚀 Quickstart: Installation

### Option 1: Source / Developer Install (Recommended)
```bash
git clone https://github.com/kuasha420/psl-agy-harness.git
cd psl-agy-harness

# Install plugin into Antigravity surfaces and register 'psl' in ~/.local/bin
./psl install --all-surfaces

# Verify workstation health, active hooks & runtimes
psl doctor
psl status
```

### Option 2: UV Tool / Pip Install (Zero-clone)
```bash
# Install the CLI executable
uv tool install git+https://github.com/kuasha420/psl-agy-harness.git

# Connect Antigravity plugin surfaces
psl install --copy --all-surfaces

# Verify
psl doctor
```

---

## 🏛️ Verified POC Components

### 1. Unified Developer CLI (`psl`)
Provides a single modular CLI entrypoint for diagnostics, tests, hooks, and mesh operations (see [docs/official-specs/cli-palette.md](docs/official-specs/cli-palette.md)):
- `psl doctor [--matrix <path>] [--heal] [--json]`: Workstation environment diagnostic & zero-sudo auto-healing.
- `psl hook <hook_name>`: Deterministic lifecycle hook dispatcher via fail-safe runner.
- `psl test [-v] [-s <dir>]`: Sub-second hermetic project test runner (<1.0s benchmark, 401 tests).
- `psl audit [stage] [options]`: Empirical telemetry laboratory extraction & analytical pipelines.
- `psl skills [name] [--sync] [--json]`: Discover, inspect, and synchronize modular product skills.
- `psl agents [name|action] [options]`: Specialist subagent catalog, scaffolding, validation & rehydration.
- `psl subagents [--json] [--brain-dir <dir>]`: Live active subagents status table & context health gauges.
- `psl status`: Unified system health, active hooks, attention horizon, skills & agents overview.
- `psl remote <exec|script|triage|socket>`: SSH-multiplexed remote mesh execution and triage (ADR-027).
- `psl auth <login|status|logout>`: GitHub organization credential management for centralized telemetry.
- `psl sync [options]`: Bi-directional telemetry synchronization with central hub (ADR-030).
- `psl install [-g|--global] [--symlink|--copy]`: Global plugin and standalone CLI installation.
- `psl uninstall [--target <path>]`: Clean global plugin uninstallation without collateral damage.

```bash
python3 -m harness.cli --help
```

### 2. Workstation Diagnostic Engine (`psl doctor`)
Audits the host environment against the 3-Tier Telemetry-Scaffolded Matrix ([matrix.json](harness/runtime/matrix.json)):
- **Tier 1 (Languages)**: Python >= 3.12 (PEP 701 f-string support), Node >= 20, `uv`, `pnpm`.
- **Tier 2 (Core SWE CLI)**: `git >= 2.38`, `gh >= 2.30`, `ripgrep >= 13.0`, `fd >= 8.7`.
- **Tier 3 (Mesh Host)**: `ssh >= 8.9`, `knot >= 1.0`.
- **Auto-Healing (`--heal`)**: Provisions user-space runtimes via `uv` with zero sudo and zero host pollution.

```bash
python3 -m harness.cli doctor
```

### 3. PreToolUse Command Safety & Hermetic Runtime Hook
Implements deterministic terminal guards before commands reach the subshell:
- **Hermetic Python Injection**: Prepends `uv`'s CPython 3.12 to `PATH` for inline utility scripts (`python3 -c`), eliminating PEP 701 syntax crashes.
- **F-String Sanitization**: Neutralizes spurious backslashes before quotes inside `{...}` expressions.
- **Surgical Grep Sanitization**: Appends `|| [ $? -eq 1 ]` to standalone `grep`/`diff` queries, neutralizing empty-match failures without masking Exit Code 2 errors.
- **Interactive Pager Suppression**: Enforces `PAGER=cat` on git and gh commands.

### 4. PreToolUse Anti-Loop Guard Hook
Tracks consecutive executions per conversation ID in `/tmp/psl_agy_harness_state/`:
- Intercepts and denies execution after 3 identical consecutive calls.
- Forces agent reasoning shifts before runaway thrashing occurs.

### 5. PostToolUse Deterministic Output Compactor
- Caps tool outputs exceeding 2KB while strictly preserving the first 500 characters, the last 1,000 characters, and all intermediate lines containing exit codes or error markers.
- Sub-millisecond latency (<0.25ms at 50KB).

---

## 🧪 Verification & Test Suite

All 401 unit, integration, and replay tests pass hermetically in **<1.0s** (ADR-015 benchmark):

```bash
python3 -m harness.cli test
```

```text
Ran 401 tests in 0.963s
OK
```

For our testing standards and verification specifications, read:
👉 **[docs/official-specs/testing-contracts.md](docs/official-specs/testing-contracts.md)**

## 🗺️ Master Roadmap & Architecture Horizons

For the complete architectural design, cognitive guardrails, and horizon breakdown, read:
👉 **[roadmap.md](roadmap.md)**

* **Horizon 0**: Empirical Ground Truth & Telemetry Ingestion (Completed & Compacted).
* **Horizon 1**: Product Foundation, Modular Subagents & Lifecycle Hooks (Completed & Compacted).
* **Horizon 2 (Active)**: Knot Hardware Mesh & Multi-Agent Fleet Scaling.


Permanent architectural decisions are recorded in the living compact ledger:
👉 **[docs/taxonomy/project-ledger.md](docs/taxonomy/project-ledger.md)**

---

## 📜 License & Governance

Licensed under the **Apache License, Version 2.0** ([LICENSE](LICENSE)).  
Copyright © 2026 Purrfect Software Limited (PSL).
