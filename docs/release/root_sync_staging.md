<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Agyis Harness Root Documentation Sync Staging (v1.0.0-rc5)

**Target Milestone**: `v1.0.0-rc5` Release Preparation  
**Publisher**: Purrfect Software Limited (PSL)  
**Document Purpose**: Authoritative staged diffs, replacement blocks, and publication drafts ready for operator review before updating root documentation files.  
**Audited Target Files**:
1. `README.md`
2. `docs/official-specs/cli-palette.md`
3. `docs/official-specs/lifecycle-hooks.md`
4. `docs/runbooks/repo-onboarding.md`
5. `docs/runbooks/telemetry-sync.md`

---

## 1. Summary of Documentation Drift on `main`

The specification mining survey (survey commit `cced547`) confirmed that while the codebase on `main` has matured to 18 CLI subcommands, 6 lifecycle hooks, 1,065 passing tests, turnkey onboarding automation, and native systemd service management, several root documentation files still reflect earlier milestones:

| Target File | Current Documented Content | Ground Truth on `main` | Drift Severity | Staged Resolution in this Document |
| :--- | :--- | :--- | :--- | :--- |
| **`README.md`** | Claims 816 tests; claims 15 commands; omits `gui` and `verify`; omits `onboard` flags; lacks `sync --service` and port collision probing. | 1,065 tests; 18 commands; `gui`, `verify`, and rich `onboard` flags active. | **High** | Section 2 provides exact unified diffs updating metrics, command counts, and command palette. |
| **`docs/official-specs/cli-palette.md`** | Titled "Consolidated 15-Command CLI Palette"; ASCII tree and body omit `onboard`, `verify`, and `gui`; lacks `sync --service`. | 18 subcommands registered in `harness/cli.py`. | **Critical** | Section 3 provides complete staged replacement text for the 18-command palette. |
| **`docs/official-specs/lifecycle-hooks.md`** | Lists 5 reference hooks; omits `token-proximity-guard`; lacks ADR-028 decoupled dirty state (`spec_dirty` vs `code_dirty`). | 6 active hooks; ADR-028 decoupled dirty state; DEF-01 dual dirty; DEF-04 pre-slice optimization. | **High** | Section 4 provides staged diffs and sections for hooks, token guard, and decoupled fence. |
| **`docs/runbooks/repo-onboarding.md`** | Details manual 7-step onboarding procedure with manual git commands and diff creation. | Turnkey `agyis onboard` automates all 7 steps with branch isolation, cache purge, and safety patches. | **Critical** | Section 5 provides modernized runbook text making `agyis onboard` the primary path. |
| **`docs/runbooks/telemetry-sync.md`** | Instructs manual shell redirection: `agyis sync --systemd > ~/.config/systemd/user/...`. | Native `agyis sync --service [install\|status\|start\|stop\|uninstall]`. | **High** | Section 6 provides modernized service daemon runbook text. |

---

## 2. Staged Diffs: `README.md`

### 2.1 Staged Unified Diff
```diff
--- a/README.md
+++ b/README.md
@@ -10,1 +10,1 @@
-[![Tests](https://img.shields.io/badge/Tests-816%2F816_Passing_(100%25)-brightgreen.svg)]()
+[![Tests](https://img.shields.io/badge/Tests-1065%2F1065_Passing_(100%25)-brightgreen.svg)]()
@@ -18,1 +18,1 @@
-> **Project State Notice**: This repository has completed empirical ingestion of **722 real-world developer sessions (219,292 steps, 160,226 tool calls)**, verified isolated lifecycle hooks, codified hermetic testing contracts (816 passing tests in <1.0s), integrated opt-in Reverse Engineer Anything (REA) cleanroom tooling (ADR-028), and packaged the unified 15-command `agyis` developer CLI suite. See [roadmap.md](roadmap.md) for the master vision and upcoming milestones.
+> **Project State Notice**: This repository has completed empirical ingestion of **722 real-world developer sessions (219,292 steps, 160,226 tool calls)**, verified isolated lifecycle hooks, codified hermetic testing contracts (1,065 passing tests, hermetic sub-second component suites), integrated opt-in Reverse Engineer Anything (REA) cleanroom tooling (ADR-028), and packaged the unified 18-command `agyis` developer CLI suite. See [roadmap.md](roadmap.md) for the master vision and upcoming milestones.
@@ -183,18 +183,21 @@
-### 1. Unified Developer CLI (`agyis`)
-Provides a single modular CLI entrypoint for diagnostics, tests, hooks, and mesh operations (see [docs/official-specs/cli-palette.md](docs/official-specs/cli-palette.md)):
-- `agyis doctor [--matrix <path>] [--heal] [--experimental-rea] [--json]`: Workstation environment diagnostic, zero-sudo auto-healing & opt-in REA provider audit.
-- `agyis hook <hook_name>`: Deterministic lifecycle hook dispatcher via fail-safe runner.
-- `agyis test [-v] [-s <dir>]`: Sub-second hermetic project test runner (<1.0s benchmark, 816 tests).
-- `agyis audit [stage] [options]`: Empirical telemetry laboratory extraction & analytical pipelines.
-- `agyis skills [name] [--sync] [--json]`: Discover, inspect, and synchronize modular product skills.
-- `agyis agents [name|action] [options]`: Specialist subagent catalog, scaffolding, validation & rehydration.
-- `agyis subagents [--json] [--brain-dir <dir>]`: Live active subagents status table & context health gauges.
-- `agyis status`: Unified system health, active hooks, attention horizon, skills & agents overview.
-- `agyis remote <exec|script|triage|socket>`: SSH-multiplexed remote mesh execution and triage (ADR-027).
-- `agyis auth <login|status|logout>`: GitHub organization credential management for centralized telemetry.
-- `agyis sync [options]`: Bi-directional telemetry synchronization with central hub (ADR-030).
-- `agyis init [path] [-s <stack>] [--experimental-rea]`: Initialize workspace project with stack skills, tagged rules & cleanroom ledger scaffolding.
-- `agyis onboard [path] [--experimental-rea]`: Guided brownfield workspace onboarding and stack discovery.
-- `agyis harmonize [path] [--dry-run]`: Harmonize legacy `.agent/` and PSL-HARNESS rules into `.agents/`.
-- `agyis install [-g|--global] [--symlink|--copy] [--experimental-rea]`: Global plugin and standalone CLI installation.
-- `agyis uninstall [--target <path>]`: Clean global plugin uninstallation without collateral damage.
+### 1. Unified Developer CLI (`agyis`)
+Provides a single modular CLI entrypoint for diagnostics, tests, hooks, and mesh operations (see [docs/official-specs/cli-palette.md](docs/official-specs/cli-palette.md)):
+- `agyis doctor [--matrix <path>] [--heal] [--experimental-rea] [--json]`: Workstation environment diagnostic, zero-sudo auto-healing, port 5432 collision probing & opt-in REA provider audit.
+- `agyis hook <hook_name>`: Deterministic lifecycle hook dispatcher via fail-safe runner.
+- `agyis test [-v] [-s <dir>]`: Hermetic project test runner (1,065 tests passing, sub-second component benchmark).
+- `agyis audit [stage] [options]`: Empirical telemetry laboratory extraction & analytical pipelines (13 stages).
+- `agyis skills [name] [--sync] [--prune-duplicates] [--json]`: Discover, inspect, synchronize, and deduplicate modular skills.
+- `agyis agents [name|action] [options]`: Specialist subagent catalog, scaffolding, validation & rehydration.
+- `agyis subagents [--json] [--brain-dir <dir>]`: Live active subagents status table & context health gauges (<2ms query).
+- `agyis status`: Unified system health, active hooks, attention horizon gauge, skills & agents overview.
+- `agyis remote <exec|script|triage|socket|screens>`: SSH-multiplexed remote mesh execution, script streaming, and triage (ADR-027).
+- `agyis auth <login|status|logout>`: GitHub organization credential management for centralized telemetry.
+- `agyis sync [--service {install,status,start,stop,uninstall}] [options]`: Bi-directional telemetry sync and native background systemd daemon (ADR-030).
+- `agyis init [path] [-s <stack>] [-r <role>] [--experimental-rea]`: Initialize workspace project with stack skills, tagged rules & cleanroom ledger scaffolding.
+- `agyis onboard [path] [flags]`: Unified turnkey workspace onboarding with branch isolation, dirty tree safety patch, cache purge, skill deduplication, and automated PR delivery.
+- `agyis harmonize [path] [--dry-run]`: Harmonize legacy `.agent/` directories and PSL-HARNESS rules into modern `.agents/`.
+- `agyis install [-g|--global] [--symlink|--copy] [--all-surfaces] [--experimental-rea]`: Global plugin and standalone CLI installation across surfaces.
+- `agyis uninstall [--target <path>]`: Clean global plugin uninstallation without collateral damage.
+- `agyis verify [--spec] [--workspace <path>] [--json]`: Formally verify cleanroom specifications and REA reconstruction obligation manifests (ADR-028).
+- `agyis gui [--devtools] [--trajectory-debug] [--toggle] [--no-popup] [--wait <sec>]`: Introspect and unlock Antigravity Electron GUI via CDP WebSocket (ADR-014).
@@ -213,2 +216,4 @@
 - **Tier 3 (Mesh Host)**: `ssh >= 8.9`, `knot >= 1.0`.
+- **Database Port Collision Probing**: Probes TCP port 5432 to identify foreign container collisions (e.g. `jasper_dev_postgres`) and recommends dynamic port re-binding.
 - **Fast-Path Invariant**: Default `agyis doctor` runs zero-delay fast-path checks (<0.05s) with strictly 0 warnings added when REA is absent, preserving sub-second benchmark latency (<1.0s).
@@ -261,11 +266,11 @@
-All 816 unit, integration, and replay tests pass hermetically in **<1.0s** (ADR-015 benchmark):
+All 1,065 unit, integration, and replay tests pass hermetically (100% pass rate):
 
 ```bash
 ./agyis test
 # or: python3 -m harness.cli test
 ```
 
 ```text
-Ran 816 tests in 0.985s
+Ran 1065 tests in 18.803s
 OK
 ```
```

---

## 3. Staged Draft: `docs/official-specs/cli-palette.md`

### 3.1 Proposed Section 1: Executive Overview & 18-Command ASCII Tree
```markdown
# Official Specification: Consolidated 18-Command CLI Palette

**Document**: Canonical CLI Subcommand Palette & Reference Guide  
**Project**: Agyis Harness for Google Antigravity™ (`agyis-harness`)  
**Publisher**: Purrfect Software Limited (PSL)  
**License**: Apache-2.0  
**Binary Entrypoint**: `agyis` (Primary) / `psl` (Deprecated Alias) / `python3 -m harness.cli`  
**Last Updated**: 2026-10-18  

---

## 1. Executive Overview

The unified developer CLI (`agyis` or `python3 -m harness.cli`, with backward-compatible alias `psl`) exposes 18 top-level subcommands implemented cleanly across `harness/commands/`, `harness/delivery/`, `harness/subagents/`, `harness/remote/`, and `harness/telemetry/`. In accordance with ADR-014 (Product vs. Project Bifurcation), all core CLI commands execute hermetically with zero mandatory dependencies on external third-party Python packages.

> [!NOTE]
> **CLI Nomenclature & Deprecation Lifecycle**: `agyis` is the primary executable. The legacy command `psl` is maintained as a backward-compatible alias with an active deprecation lifecycle (emitting `DeprecationWarning: 'psl' is deprecated and will be removed in 3 months. Use 'agyis' instead.` to `stderr`).

```text
agyis [-h] [-v]
  ├── doctor        Audit host workstation runtimes, port collisions, and auto-heal
  ├── hook          Run a lifecycle hook handler directly via fail-safe runner
  ├── test          Run hermetic test suites with benchmark timing
  ├── audit         Run empirical telemetry laboratory extraction & analytics (13 stages)
  ├── skills        List, inspect, synchronize, and deduplicate modular skills
  ├── agents        Catalog, inspect, create, validate, and rehydrate specialist subagents
  ├── subagents     List active subagents and live context health gauges
  ├── status        Print harness health, active hooks, attention horizon & telemetry summary
  ├── remote        Remote agentic execution, SSH multiplexing & cloud/mesh triage (ADR-027)
  ├── auth          Manage GitHub organization authentication for central hub sync
  ├── sync          Bi-directional telemetry sync and native background systemd daemon (ADR-030)
  ├── init          Initialize workspace project with stack skills, tagged rules & cleanroom ledgers
  ├── harmonize     Harmonize legacy .agent/ directories and PSL-HARNESS rules into .agents/
  ├── onboard       Unified brownfield workspace onboarding with branch isolation, cache purge & PR delivery
  ├── install       Install Agyis harness globally as Google Antigravity plugin across surfaces
  ├── uninstall     Uninstall Agyis harness global plugin cleanly without collateral damage
  ├── verify        Formally verify cleanroom specifications and REA reconstruction manifests (ADR-028)
  └── gui           Introspect and control Antigravity Electron GUI via CDP WebSocket (ADR-014)
```
```

### 3.2 Proposed New Reference Entries for `onboard`, `verify`, `gui`, and `sync --service`
```markdown
### 14. `onboard`
* **Syntax**: `agyis onboard [path] [flags]`
* **Purpose**: Turnkey brownfield workspace onboarding combining git topology probing, legacy `.agent/` archiving and deterministic 2-step pruning, decoupled language & architectural role presets, explicit skills provisioning, cache purging, git exclusion configuration, and pull request creation.
* **Flags**:
  - `path`: Target workspace path (defaults to current directory).
  - `--lang`, `--stack`, `-s`: Language preset (`typescript`, `node`, `javascript`, `python`, `rust`, `go`, `systems`, `shell`, `auto`).
  - `--role`, `-r`: Architectural role preset (`backend`, `frontend`, `fullstack`, `cli`, `library`, `mobile`, `desktop_gui`, `media`, `audio`, `infra`).
  - `--skills`: Comma-separated list of explicit skills to provision (overrides preset inference).
  - `--subproject`: Scoped subproject relative path for monorepos (e.g. `services/billing`).
  - `--create-branch [name]`: Dedicated onboarding branch isolation (defaults to `chore/agyis-harness-onboarding`).
  - `--allow-dirty`: Proceed on a dirty tree by automatically exporting `.agents/artifacts/wip-safety-pre-onboard.patch`.
  - `--purge-caches`: Purge build caches (`.next`, `.turbo`) before verification (default: True).
  - `--no-cache-purge`: Disable automatic build cache purging.
  - `--prune-legacy`: Safely archive legacy `.agent/` to tar.gz and prune (default: True).
  - `--no-prune`: Retain legacy `.agent/` directory on disk.
  - `--pr`, `--open-pr`: Open GitHub Pull Request via `gh pr create` upon verified test pass.
  - `--dry-run`: Preview all onboarding operations without filesystem or git mutations.
  - `--json`: Output machine-readable structured JSON report.
  - `--experimental-rea`: Provision Reverse Engineer Anything cleanroom specifications and ledgers.
* **Exit Codes**: `0` on success; `1` on dirty tree without `--allow-dirty`, invalid git repository, or missing path.

### 17. `verify`
* **Syntax**: `agyis verify [--spec] [--workspace <path>] [--json]`
* **Purpose**: Cleanroom specification and reconstruction verification engine (ADR-028).
* **Flags**:
  - `--spec`: Verifies cleanroom specifications in `docs/specs/**`. Asserts zero executable code files exist inside specification directories and resets `spec_dirty = False` in the completion fence.
  - Without `--spec`: Delegates to `rea verify-reconstruction` to verify typed obligations in `.agents/ledger/manifest.json`.
  - `--workspace`, `-w`: Target workspace root path (default: current directory).
  - `--json`: Structured JSON verification output.
* **Exit Codes**: `0` on satisfied specifications/manifests; `1` if executable code exists in `docs/specs/` or if obligations remain unsatisfied.

### 18. `gui`
* **Syntax**: `agyis gui [--devtools] [--trajectory-debug] [--toggle] [--no-popup] [--wait <sec>] [--port-file <path>] [--json]`
* **Purpose**: Introspect and control Google Antigravity's Electron GUI via Chromium DevTools Protocol (CDP) WebSocket (ADR-014 / REA-SPEC-001).
* **Flags**:
  - `--trajectory-debug`: Injects developer flags into `localStorage` and opens Trajectory Debug View (`?trajectoryDebugOpen=true`) (default action).
  - `--no-popup`, `--setup-only`: Injects flags and hotkeys (F12, Ctrl+Shift+T) without opening the modal popup.
  - `--toggle`: Toggles Trajectory Debug View open/closed state.
  - `--devtools`: Inspects active port and prints Chrome Inspect and direct webview URLs.
  - `--wait <sec>`: Poll timeout for active Antigravity webview to become ready.
  - `--json`: Structured JSON connection and injection report.
* **Exit Codes**: `0` on successful injection; `1` if Antigravity GUI is not running or CDP fails.

### Updated Flag in `sync`:
* `--service {install,status,start,stop,uninstall}`: Manages native background synchronization systemd user service.
```

---

## 4. Staged Draft: `docs/official-specs/lifecycle-hooks.md`

### 4.1 Update Section 3: 6 Active Reference Hooks
```markdown
## 3. Reference Implementation: `agyis-harness` Hooks

In `harness/hooks/`, we provide 6 deterministic hooks registered in `hooks.json`:
1. `command_safety_hook.py`: PreToolUse shell execution sanitizer, Python >= 3.12 uv runtime injector, and grep pattern probing exit normalizer (ADR-013).
2. `anti_loop_hook.py`: PreToolUse repetitive call breaker and Strict Reactive Wait enforcer.
3. `output_compactor_hook.py`: PostToolUse deterministic 2KB output compactor with DEF-04 pre-slice optimization for massive dumps.
4. `completion_fence_hook.py`: PreToolUse/PostToolUse/Stop verification fence with ADR-028 decoupled dirty state (`code_dirty` vs `spec_dirty`).
5. `token_proximity_guard.py`: PreToolUse context accumulation monitor decoding SQLite protobuf metadata and emitting ANSI threshold gauges.
6. `anti_drift_hook.py`: PreToolUse plan adherence guard and Auditor write-block enforcer.
```

### 4.2 Staged Section 3.2: `psl-token-proximity-guard` (New Section)
```markdown
### 3.2 The `psl-token-proximity-guard` Contract

The token proximity guard monitors active session context accumulation to warn agents before they hit the catastrophic 50k token context cliff.

#### A. Registration in `hooks.json`
```json
{
  "psl-token-proximity-guard": {
    "PreToolUse": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 -m harness.hooks.runner token-proximity",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

#### B. Decoding & Thresholds
1. **SQLite Sampling**: Directly queries `~/.gemini/antigravity/conversations/*.db` using read-only URI mode (`file:<path>?mode=ro`) to prevent database lock contention.
2. **Protobuf Extraction**: Reads the latest step from the `steps` table and decodes binary protobuf field 9 to extract exact prompt and cached tokens.
3. **Threshold Indicators**:
   - `< 35,000 tokens`: Silent (normal operation).
   - `35,000 - 44,999 tokens`: Emits an ANSI amber warning gauge to `stderr` advising approaching horizon limits.
   - `>= 45,000 tokens`: Emits a bold ANSI red alert and terminal bell (`\a`) warning that the 50k compaction threshold is imminent.
4. **Fail-Open Invariant**: Always outputs `{"decision": "allow"}` and exits 0. Tool calls are never interrupted.
```

### 4.3 Staged Update to Section 3.1: ADR-028 Decoupled Dirty State
```markdown
#### B. Operational State Machine & Decoupled Dirty State (ADR-028)

The completion fence decouples dirty state into two independent flags:

1. **`code_dirty` State**:
   - Set when any file matching `CODE_EXTENSIONS` (`.py`, `.ts`, `.rs`, `.go`, `.c`, `.sh`) outside specification directories is modified.
   - Cleared ONLY when the active repository test runner (`agyis test`, `pytest`, `npm test`, `cargo test`) runs and exits with code 0.
   - When active, blocks agent `Stop` with:
     `Execute active repository test suite before declaring completion.`

2. **`spec_dirty` State**:
   - Set when cleanroom contracts (`docs/specs/**`, `.agents/ledger/**`) with declarative extensions (`.md`, `.json`, `.yaml`, `.proto`) are modified.
   - Does NOT demand unit tests!
   - Cleared when `agyis verify --spec` exits 0 or when cleanroom manifest is verified via `rea verify-reconstruction`.
   - When active, blocks agent `Stop` with:
     `Execute cleanroom verification before declaring completion: 'agyis verify --spec'`

3. **Code-in-Specs Dual Dirty Guard (DEF-01)**:
   - If an agent writes executable code (`.py`, `.ts`, `.sh`) into `docs/specs/`, the fence sets **BOTH `code_dirty = True` and `spec_dirty = True`**, preventing agents from evading unit test requirements.

4. **Ephemeral Paths**:
   - Scratch directories (`.rea/**`, `decompiled/**`, `artifacts/rea/**`, `/scratch/`, or temporary paths outside workspace root) never mark state dirty.

5. **Anti-Deadlock Safety Valve**:
   - If blocked twice consecutively (`block_count >= 2`), the safety valve trips and allows termination, preventing infinite loops.
```

---

## 5. Staged Draft: `docs/runbooks/repo-onboarding.md`

### 5.1 Modernized Turnkey Runbook Text
```markdown
# 📦 Canonical Repository Onboarding Runbook (Modernized for v1.0.0-rc5)

This operational runbook provides the definitive protocol for onboarding internal, client, or open-source repositories to the **Agyis Harness** runtime environment.

---

## 1. Automated Turnkey Onboarding (`agyis onboard`)

Rather than executing a multi-step manual procedure, onboarding is executed through the unified `agyis onboard` engine.

### Quick Start:
```bash
# Move into target repository
cd /path/to/target-repo

# Run turnkey onboarding with branch isolation and PR delivery
agyis onboard . --lang python --role backend --create-branch --pr
```

### What `agyis onboard` executes automatically:
1. **Host Safety Guard**: Verifies target is not the Agyis harness development repository itself.
2. **Git Topology Probing**: Identifies active branch, default upstream remote, and checks for uncommitted changes.
3. **Dirty Tree Safety Patch**: If uncommitted changes exist and `--allow-dirty` is passed, writes `.agents/artifacts/wip-safety-pre-onboard.patch`.
4. **Branch Isolation**: Checks out a dedicated onboarding branch (default: `chore/agyis-harness-onboarding`).
5. **Build Cache Purge**: Automatically purges `.next`, `.turbo`, and `node_modules/.cache` to prevent type collisions.
6. **Harmonization & Archival**: Archives legacy `.agent/` directories to `.agents/archive/*.tar.gz` and manifests before executing deterministic 2-step deletion.
7. **Skill Provisioning & Deduplication**: Provisions tailored skills and unlinks redundant workspace skills that duplicate global plugin skills.
8. **Git Hygiene**: Updates `.git/info/exclude` to ignore archives and safety patches.
9. **Native Verification**: Automatically runs the repository test suite to verify 0 regressions.
10. **PR Delivery**: Automatically opens a pull request targeting the upstream repository via `gh pr create`.

---

## 2. Monorepo Subproject Onboarding
For monorepos containing multiple independent applications or packages:
```bash
# Onboard a specific subproject inside a monorepo
agyis onboard . --subproject services/billing --lang typescript --role backend --create-branch
```

---

## 3. Architectural Reference: The 7 Under-the-Hood Steps
*(Retained for debugging and systems understanding)*
- **Step 1: Tree Triage**: `git status --porcelain` check.
- **Step 2: Branch Sync**: `git fetch origin` & checkout base branch.
- **Step 3: Harmonization**: `agyis harmonize` rules and archive `.agent/`.
- **Step 4: Skill Scaffolding**: `agyis skills --sync`.
- **Step 5: Git Exclusion**: Add `.agents/archive/` to `.git/info/exclude`.
- **Step 6: Automated Test Verification**: Run project test command (exit code 0).
- **Step 7: Pull Request Creation**: `gh pr create`.
```

---

## 6. Staged Draft: `docs/runbooks/telemetry-sync.md`

### 6.1 Modernized Telemetry Sync Runbook Text
```markdown
### 2.5 Automated Background Daemon & Systemd Unit

To keep local developer session telemetry continuously synchronized with the central PSL telemetry hub, manage the background daemon using the native `agyis sync --service` subcommand:

```bash
# Install, reload daemon, and enable user service
agyis sync --service install

# Optional: Configure a custom poll interval (default is 5.0s)
agyis sync --service install --interval 10.0

# Query service status (returns exit code 0 when active)
agyis sync --service status

# Query service status in machine-readable JSON
agyis sync --service status --json

# Start or stop the service
agyis sync --service start
agyis sync --service stop

# Cleanly stop, disable, and remove the service unit
agyis sync --service uninstall
```

> [!NOTE]
> **Container and Headless Fallback**: In Docker containers or headless environments lacking `systemd --user`, use the foreground watch daemon:
> ```bash
> agyis sync --watch --interval 10.0
> ```
```
