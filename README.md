<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Agyis Harness for Google Antigravity™ (agyis-harness)

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Platform](https://img.shields.io/badge/Platform-Google_Antigravity-4285F4.svg)](https://antigravity.google)
[![Status](https://img.shields.io/badge/Status-Active_Development_(Research_&_POC)-orange.svg)]()
[![Tests](https://img.shields.io/badge/Tests-1065%2F1065_Passing_(100%25)-brightgreen.svg)]()

> An open-source empirical audit pipeline and reference extension harness for **Google Antigravity™** by **Purrfect Software Limited (PSL)** under the **Apache-2.0** license.

---

> [!NOTE]
> **Project State Notice**: This repository has completed empirical ingestion of **722 real-world developer sessions (219,292 steps, 160,226 tool calls)**, verified isolated lifecycle hooks, codified hermetic testing contracts (1,065 passing tests, hermetic sub-second component suites), integrated opt-in Reverse Engineer Anything (REA) cleanroom tooling (ADR-028), and packaged the unified 18-command `agyis` developer CLI suite. See [roadmap.md](roadmap.md) for the master vision and upcoming milestones.

> [!IMPORTANT]
> **CLI Nomenclature & Backward-Compatibility Lifecycle**: The primary CLI executable is **`agyis`**. The legacy command **`psl`** is maintained as a backward-compatible alias with an active deprecation lifecycle (emitting `DeprecationWarning: 'psl' is deprecated and will be removed in 3 months. Use 'agyis' instead.` to `stderr`). All scripts, documentation, and workflows should use `agyis`.

---

## 🎯 North Star & PSL Motivation

Google's Gemini models—with **Gemini 3.8 Flash** as our primary high-throughput SWE workhorse and **Gemini 3.1 Pro** as our deep architectural reasoning model—demonstrate market-leading long-context reasoning, tool fidelity, and price-to-performance efficiency for software engineering automation. However, developer productivity in long-horizon coding tasks is frequently constrained by harness-level friction:

1. **Context Cliffs & Output Flooding**: Unpruned tool outputs dump thousands of lines into context, accelerating the 100k-token cognitive degradation cliff.
2. **Terminal Desyncs & False-Positive Failures**: 98.4% of all tool failures occur in `run_command`, driven by benign exit code 1 panics (grep/diff), pyenv/conda shim hijacking, and interactive subshell hangs.
3. **Premature Convergence & Cognitive Drift**: In deep sessions (>100k tokens), models succumb to "chatbot seduction", confusing speculative text proposals with working code, rationalizing incomplete work, and perseverating on repetitive thought mantras.
4. **Environment Version Mismatch**: Models trained on modern syntax (e.g. Python >= 3.12 PEP 701 f-strings) crash when host workstations run outdated pyenv shims (Python 3.10), wasting context on syntax retries.

### Our Strategy: Build On, Not Against, Official Interfaces
Rather than creating an isolated, competing framework that reinvents agent execution, `agyis-harness`:
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

## 🚀 Quickstart: Installation & Coexistence

### 1. Workstation-Wide Setup (Global Plugin & CLI)

The global installation deploys the reference harness plugin into Antigravity surfaces, registers the unified `agyis` CLI in `~/.local/bin` (with backward-compatible alias `psl`), and activates deterministic lifecycle hooks.

#### Option A: Source / Developer Install (Recommended for Development)
```bash
git clone https://github.com/kuasha420/agyis-harness.git
cd agyis-harness

# Install plugin into Antigravity surfaces and register 'agyis' in ~/.local/bin
./agyis install --all-surfaces

# Verify workstation health, active hooks & runtimes
agyis doctor
agyis status
```

#### Option B: Standalone / Zero-Clone Install (`uv tool`)
```bash
# Install the standalone CLI executable into an isolated environment
uv tool install git+https://github.com/kuasha420/agyis-harness.git

# Deploy plugin bundle to Antigravity surfaces
agyis install --copy --all-surfaces

# Verify installation
agyis doctor
```

---

### 2. Project-Specific Installation (Workspace Skills & Tooling)

When working inside a specific software repository, you can initialize, configure, and isolate project-tailored skills, specialist agents, rules, and runtimes without dirtying global settings or external workspaces.

#### Step 1: Synchronize Modular Skills into the Project
From inside any project repository, you can synchronize all skills or selectively deploy only the skills required for your technology stack or workflow:
```bash
cd /path/to/my-project

# 1. Sync tailored to your tech stack (auto-detects package.json, pyproject.toml, Cargo.toml, go.mod)
agyis skills --sync --stack auto

# 2. Or sync by explicit stack preset (python, typescript, rust, go, systems, shell, backend)
agyis skills --sync --stack python

# 3. Or sync by functional group preset (stack, testing/runners, ops/workstation, workflow/ladder)
agyis skills --sync --group ops

# 4. Or sync specific skills by name
agyis skills psl-stack-python --sync
agyis skills --sync --skills "psl-stack-shell, audio-ops, git-worktree-ops"

# 5. Or sync all modular skills (including reverse-engineer-anything)
agyis skills --sync
```
*Tip: You can also author custom project-specific skills by placing a `SKILL.md` directly into `.agents/skills/<skill-name>/SKILL.md`.*

#### Step 2: Scaffold Project-Tailored Specialist Agents
Generate specialist agent personas that automatically ground themselves into your repository's detected languages (`pyproject.toml`, `package.json`, `Cargo.toml`), test runners, key commands, and invariants:
```bash
# Scaffold a project-specific builder / implementer agent
agyis agents create my-builder --archetype executioner --scope project

# Or synchronize the full specialist roster into <my-project>/.agents/agents/
agyis agents --sync
```

#### Step 3: Configure Project Tooling & Hermetic Runtimes
- **Automatic `.venv` Promotion**: When you execute `agyis` inside a project containing a local Python virtual environment (`.venv/`), the launcher automatically promotes execution to `.venv/bin/python`.
- **Project Environment Diagnostics**:
  ```bash
  agyis doctor                               # Audits project against 3-tier runtime matrix
  agyis doctor --heal                        # Zero-sudo user-space repair if tools missing
  agyis doctor --experimental-rea            # Deep REA provider & cleanroom audit
  ```
- **Hermetic Testing Benchmark**:
  ```bash
  agyis test                                 # Executes tests in <1.0s and resets completion fences
  ```

#### Step 4: Workspace Initialization & Rule Harmonization
- **Project Initialization**:
  ```bash
  agyis init                                 # Auto-detects tech stack and scaffolds .agents/ with tagged rules
  agyis init --experimental-rea              # Scaffolds .agents/ledger/ for cleanroom binary reconstruction
  ```
- **Harmonize Legacy Configurations**:
  ```bash
  agyis harmonize                            # Migrates legacy .agent/ to .agents/ and upgrades tagged rules
  ```

---

### 3. Architecture: Global vs. Local Precedence Hierarchy (ADR-030)

The Antigravity engine and PSL Harness operate on a strict **3-Tier Precedence Hierarchy** (`CoexistenceEngine`). High-precedence layers cleanly override lower-precedence defaults:

```text
[Layer 3: Workspace Local] (<project-root>/.agents/ or project root) -- HIGHEST PRECEDENCE
         │ (Overrides user defaults and plugin fallbacks)
         ▼
[Layer 2: Workstation User] (~/.gemini/antigravity/, ~/.gemini/config/)
         │ (Overrides bundled plugin defaults)
         ▼
[Layer 1: Global Plugin] (~/.gemini/config/plugins/agyis-harness/ or harness/) -- DEFAULT FALLBACK
```

#### Component Comparison Matrix

| Component | Workstation-Wide (Global) | Workspace / Project-Specific (Local) | Resolution & Override Semantics |
| :--- | :--- | :--- | :--- |
| **Modular Skills** | `~/.gemini/config/skills/`<br>or bundled in plugin | `<project>/.agents/skills/<skill>/SKILL.md` | **Layer 3 > 2 > 1**: A local skill in `.agents/skills/` overrides any global skill with the same name. |
| **Specialist Agents** | `~/.gemini/config/agents/<name>.md`<br>or bundled in plugin | `<project>/.agents/agents/<name>.md` | **Layer 3 > 2 > 1**: Scaffolds automatically ground into local package manifests; local agents take precedence. |
| **Agent Rules** | `~/.gemini/config/AGENTS.md`<br>`~/.gemini/config/rules/*.md` | `<project>/AGENTS.md`<br>`<project>/.agents/rules/*.md` | **Layer 3 > 2**: Local project rules take precedence, providing repository-specific constraints on top of global standards. |
| **Developer CLI & Launcher** | `~/.local/bin/agyis`<br>`~/.gemini/antigravity/bin/agyis` | `./agyis` in repo root | Global launcher is universally available in `$PATH`; auto-promotes to project `.venv` when run inside a repo. |
| **Tooling & Runtimes** | System `$PATH`, `uv` global python | Project `.venv`, `node_modules` | Project virtual environments take priority during task execution; `agyis doctor` audits local versions. |
| **Lifecycle Hooks** | Global `hooks.json` across surfaces | Project `hooks.json` | Deterministic fail-safe runner intercepts tool calls across all sessions. |
| **Git Hygiene & State** | `~/.local/state/agyis/` | `.git/info/exclude` | `agyis install` configures `.git/info/exclude` so untracked local state never pollutes git status. |

---

## 🏛️ Verified POC Components

### 1. Unified Developer CLI (`agyis`)
Provides a single modular CLI entrypoint for diagnostics, tests, hooks, and mesh operations (see [docs/official-specs/cli-palette.md](docs/official-specs/cli-palette.md)):
- `agyis doctor [--matrix <path>] [--heal] [--experimental-rea] [--json]`: Workstation environment diagnostic, zero-sudo auto-healing, port 5432 collision probing & opt-in REA provider audit.
- `agyis hook <hook_name>`: Deterministic lifecycle hook dispatcher via fail-safe runner.
- `agyis test [-v] [-s <dir>]`: Hermetic project test runner (1,065 tests passing, sub-second component benchmark).
- `agyis audit [stage] [options]`: Empirical telemetry laboratory extraction & analytical pipelines (13 stages).
- `agyis skills [name] [--sync] [--prune-duplicates] [--json]`: Discover, inspect, synchronize, and deduplicate modular skills.
- `agyis agents [name|action] [options]`: Specialist subagent catalog, scaffolding, validation & rehydration.
- `agyis subagents [--json] [--brain-dir <dir>]`: Live active subagents status table & context health gauges (<2ms query).
- `agyis status`: Unified system health, active hooks, attention horizon gauge, skills & agents overview.
- `agyis remote <exec|script|triage|socket|screens>`: SSH-multiplexed remote mesh execution, script streaming, and triage (ADR-027).
- `agyis auth <login|status|logout>`: GitHub organization credential management for centralized telemetry.
- `agyis sync [--service {install,status,start,stop,uninstall}] [options]`: Bi-directional telemetry sync and native background systemd daemon (ADR-030).
- `agyis init [path] [-s <stack>] [-r <role>] [--experimental-rea]`: Initialize workspace project with stack skills, tagged rules & cleanroom ledger scaffolding.
- `agyis onboard [path] [flags]`: Unified turnkey workspace onboarding with branch isolation, dirty tree safety patch, cache purge, skill deduplication, and automated PR delivery.
- `agyis harmonize [path] [--dry-run]`: Harmonize legacy `.agent/` directories and PSL-HARNESS rules into modern `.agents/`.
- `agyis install [-g|--global] [--symlink|--copy] [--all-surfaces] [--experimental-rea]`: Global plugin and standalone CLI installation across surfaces.
- `agyis uninstall [--target <path>]`: Clean global plugin uninstallation without collateral damage.
- `agyis verify [--spec] [--workspace <path>] [--json]`: Formally verify cleanroom specifications and REA reconstruction obligation manifests (ADR-028).
- `agyis gui [--devtools] [--trajectory-debug] [--toggle] [--no-popup] [--wait <sec>]`: Introspect and unlock Antigravity Electron GUI via CDP WebSocket (ADR-014).

> *Note: `psl` remains available as a backward-compatible alias with a deprecation notice.*

```bash
agyis --help
# or: python3 -m harness.cli --help
```

### 2. Workstation Diagnostic Engine (`agyis doctor`)
Audits the host environment against the 3-Tier Telemetry-Scaffolded Matrix ([matrix.json](harness/runtime/matrix.json)):
- **Tier 1 (Languages)**: Python >= 3.12 (PEP 701 f-string support), Node >= 20, `uv`, `pnpm`.
- **Tier 2 (Core SWE CLI)**: `git >= 2.38`, `gh >= 2.30`, `ripgrep >= 13.0`, `fd >= 8.7`.
- **Tier 3 (Mesh Host)**: `ssh >= 8.9`, `knot >= 1.0`.
- **Database Port Collision Probing**: Probes TCP port 5432 to identify foreign container collisions (e.g. `jasper_dev_postgres`) and recommends dynamic port re-binding.
- **Fast-Path Invariant**: Default `agyis doctor` runs zero-delay fast-path checks (<0.05s) with strictly 0 warnings added when REA is absent, preserving sub-second benchmark latency (<1.0s).
- **Opt-In REA Provider Audit (`--experimental-rea`)**: Audits Reverse Engineer Anything (REA >= 6.0.0), MCP server registration, dynamic JDK 21+ discovery ladder, Ghidra 12.1+ headless analyzer, Hopper display socket contract, and optional IDA Pro/JADX supervisor isolation flags.
- **Auto-Healing (`--heal`)**: Provisions user-space runtimes via `uv` (and installs `rea-agents` + MCP registration when combined with `--experimental-rea`) with zero sudo and zero host pollution.

```bash
agyis doctor
agyis doctor --experimental-rea
agyis doctor --experimental-rea --heal
```

### 3. PreToolUse Command Safety & Hermetic Runtime Hook
Implements deterministic terminal guards before commands reach the subshell:
- **Hermetic Python Injection**: Prepends `uv`'s CPython 3.12 to `PATH` for inline utility scripts (`python3 -c`), eliminating PEP 701 syntax crashes.
- **F-String Sanitization**: Neutralizes spurious backslashes before quotes inside `{...}` expressions.
- **Surgical Grep Sanitization**: Appends `|| [ $? -eq 1 ]` to standalone `grep`/`diff` queries, neutralizing empty-match failures without masking Exit Code 2 errors.
- **Interactive Pager Suppression**: Enforces `PAGER=cat` on git and gh commands.
- **REA Subshell PATH Shims**: Automatically injects `~/.local/share/pnpm`, `~/.npm-global/bin`, and `~/.local/bin` shims for `rea` invocations, permanently resolving Exit Code 127 in non-login subshells (DEF-05).

### 4. PreToolUse Anti-Loop Guard Hook
Tracks consecutive executions per conversation ID in `/tmp/agyis_harness_state/` (or `/tmp/psl_agy_harness_state/`):
- Intercepts and denies execution after 3 identical consecutive calls.
- Forces agent reasoning shifts before runaway thrashing occurs.
- **Cleanroom Bounded Quotas**: Enforces an elevated sliding-window quota (up to 8 calls in a 15-call window) for cleanroom specifications (`docs/specs/**`) and obligation ledgers (`.agents/ledger/**`), while strictly denying $\ge 3$ consecutive repeats (DEF-02).
- **Verification Reset**: REA verification commands (`rea verify-reconstruction`, `rea test`, `agyis verify`) immediately reset verification loop counters.

### 5. PostToolUse Deterministic Output Compactor
- Caps tool outputs exceeding 2KB while strictly preserving the first 500 characters, the last 1,000 characters, and all intermediate lines containing exit codes or error markers.
- Sub-millisecond latency (<0.25ms at 50KB).
- **Disassembly Pre-Slice Character Bounding (DEFECT-001 / DEF-04)**: For massive disassembly dumps exceeding 200KB, slices bounded 100KB head and tail character chunks *before* running `.splitlines()`, bounding preserved diagnostic lines to a maximum of 50 lines to prevent CPU exhaustion and hook timeouts. Preserves structured JSON framing brackets.

### 6. Phase-Aware Cleanroom Completion Fence Gate & REA Harmonization (ADR-028)
Formal cleanroom reconstruction architecture resolving Issue #44 (doctor latency degradation) and Issue #45 (cleanroom specification deadlock):
- **Decoupled Dirty State Tracking (DEF-01)**: Decouples declarative specification authoring (`spec_dirty`) from executable code modifications (`code_dirty`). Agents performing binary analysis and authoring specifications in `docs/specs/**` (`.md`, `.json`, `.yaml`, `.proto`, `.schema`) are never blocked by irrelevant software unit test demands.
- **Code-in-Specs Guard**: Any modified file in `docs/specs/**` bearing executable code extensions (`.py`, `.ts`, `.rs`, `.go`, `.sh`) triggers dual dirty state (`code_dirty = True`), enforcing unit test verification before completion.
- **Formal Manifest Clearance (DEF-06)**: Validates cleanroom clearance manifests in `.agents/ledger/manifest.json` against typed schemas (`status: "verified"`, 64-character SHA-256 `evidence_hash`, and satisfied `obligations`). Unverified stops provide actionable cleanroom guidance:
  ```text
  Cleanroom Verification Required: Unverified cleanroom contract edits detected in: <files>.
  Execute 'rea verify-reconstruction' or 'agyis verify --spec' before stopping.
  ```
- **Modular `reverse-engineer-anything` Skill**: Packages the upstream `morluto/rea` skill (version 42, 207 MCP tools) with 6 exhaustive reference guides (`android-applications.md`, `connection-and-recovery.md`, `evidence-workflows.md`, `javascript-applications.md`, `native-and-artifacts.md`, `runtime-observation.md`).
- **Scratch Path Isolation**: Ephemeral analysis scratch paths (`.rea/**`, `decompiled/**`, `artifacts/rea/**`) are exempted from dirty-state tracking.
- **Official References**: Read [ADR-028: Opt-in REA Tooling and Cleanroom Reconstruction Harmonization](docs/adr/ADR-028-opt-in-rea-cleanroom-harmonization.md) and [docs/official-specs/rea-antigravity-architecture.md](docs/official-specs/rea-antigravity-architecture.md) (`PSL-SPEC-2026-REA-001`).

---

## 🧪 Verification & Test Suite

All 1,065 unit, integration, and replay tests pass hermetically (100% pass rate):

```bash
./agyis test
# or: python3 -m harness.cli test
```

```text
Ran 1065 tests in 20.405s
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

Licensed under the **Apache License, Version 2.0** ([LICENSE](LICENSE)) under the **CSP-IP Framework**.  
Copyright © 2026 Arafat Zahan (@kuasha420)  
Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)  
Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)
