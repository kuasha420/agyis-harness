<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Agyis Harness End-User Guide (v1.0.0-rc5)

**Target Audience**: Developers, Autonomous Agent Operators, Platform Engineers  
**Publisher**: Purrfect Software Limited (PSL)  
**Binary Entrypoint**: `agyis` (Primary) | `python3 -m harness.cli` | `psl` (Deprecated Alias)  
**Release Milestone**: `v1.0.0-rc5`  
**License**: Apache-2.0  

---

## 1. Getting Started & Harness Overview

### 1.1 What is Agyis Harness?
**Agyis Harness** (`agyis-harness`, formerly `psl-agy-harness`) is an open-source, empirical engineering harness and reference extension framework for **Google Antigravity™**. It bridges the gap between frontier reasoning models (Gemini 3.8 Flash, Gemini 3.1 Pro) and the real-world friction of deep, multi-hour software engineering sessions.

Frontier models excel at code reasoning, tool fidelity, and long-context synthesis. However, deep coding sessions (>50 steps, >100k tokens) consistently suffer from predictable harness-level failure modes:
1. **Context Cliff & Output Flooding**: Unpruned tool outputs dump thousands of lines into the conversation window, exhausting model attention and precipitating cognitive degradation.
2. **Terminal Invariant Panics**: 98.4% of all tool failures stem from `run_command` desyncs (benign exit code 1 panics from `grep` or `diff`, pyenv/conda shim hijacking, interactive command hangs).
3. **Premature Convergence & Cognitive Drift**: Under context pressure, agents declare victory prematurely, confusing text proposals with working code or getting trapped in repetitive thought mantras.
4. **Environment Drift**: Mismatches between model-generated modern syntax (Python >= 3.12 PEP 701 f-strings) and outdated host workstation shims (Python 3.10) cause avoidable syntax retries.

Agyis Harness solves these friction points **in deterministic code and lifecycle hooks, not prompt tokens**. By intercepting and sanitizing tool executions, managing workstation environments, compacting outputs, and enforcing stop-hook verification fences, Agyis Harness preserves model cognition for actual task reasoning.

### 1.2 Core Architectural Principles
- **Build On, Not Against, Official Surfaces**: Operates strictly within official Google Antigravity extension points: lifecycle hooks (`PreToolUse`, `PostToolUse`, `Stop`), custom agent markdown personas, modular skills, and Model Context Protocol (MCP) servers.
- **Zero External Runtime Dependencies (ADR-014)**: The core harness engine (`harness/`) requires **zero third-party Python packages** (`pyproject.toml` declares `dependencies = []`). It runs entirely on the standard library of CPython >= 3.12 (`pathlib`, `shutil`, `subprocess`, `urllib`, `socket`, `sqlite3`, `json`, `tarfile`, `hashlib`).
- **Sub-Second Hermetic Verification (ADR-015)**: Harness components and project test runners execute in sub-second benchmark latency (<1.0s) inside isolated clean-room environments.
- **Three-Layer Configuration Architecture**:
  * **Layer 1 (Global Plugin)**: Bundled runtime, certified specialist agents, modular skills, and fail-safe hooks installed in `~/.gemini/antigravity/` and surfaces.
  * **Layer 2 (User Configuration)**: Workstation overrides and global rules in `~/.gemini/config/`.
  * **Layer 3 (Workspace Project)**: Repository-level rules (`<repo>/AGENTS.md`), project-specific skills (`<repo>/.agents/skills/`), and cleanroom ledgers (`<repo>/.agents/ledger/`). **Precedence: Layer 3 > Layer 2 > Layer 1**.

### 1.3 Unified 18-Command CLI Palette
Agyis Harness provides a single modular CLI entrypoint with 18 commands:

```text
agyis [-h] [-v]
  ├── doctor        Audit host workstation runtimes and execute auto-healing
  ├── hook          Run a lifecycle hook handler directly via fail-safe runner
  ├── test          Run hermetic test suites with sub-second benchmark timing
  ├── audit         Run empirical telemetry laboratory extraction & analytics (13 stages)
  ├── skills        Discover, inspect, sync, and deduplicate modular skills
  ├── agents        Catalog, inspect, scaffold, validate, and rehydrate specialist subagents
  ├── subagents     Inspect active subagents and live context health gauges
  ├── status        Print unified system health, active hooks, and telemetry overview
  ├── remote        SSH-multiplexed remote execution, script streaming & triage (ADR-027)
  ├── auth          Manage GitHub organization authentication for central hub sync
  ├── sync          Bi-directional telemetry synchronization & background daemon (ADR-030)
  ├── init          Initialize workspace with stack skills, tagged rules & cleanroom ledgers
  ├── harmonize     Harmonize legacy .agent/ directories and PSL-HARNESS rules into .agents/
  ├── onboard       Unified turnkey brownfield workspace onboarding and PR delivery
  ├── install       Install Agyis harness globally as Google Antigravity plugin
  ├── uninstall     Uninstall global plugin cleanly without collateral damage
  ├── verify        Formally verify cleanroom specifications and REA reconstruction manifests
  └── gui           Introspect and control Antigravity Electron GUI via CDP WebSocket (ADR-014)
```

> **Legacy Compatibility**: The legacy CLI command `psl` is maintained as a backward-compatible alias. Invoking `psl` emits a notice to `stderr`:  
> `DeprecationWarning: 'psl' is deprecated and will be removed in 3 months. Use 'agyis' instead.`  
> All user scripts and workflows should use `agyis`.

---

## 2. Global Installation & Workstation Diagnostics

### 2.1 Global Installation (`agyis install`)
Agyis Harness installs globally as a recognized Google Antigravity plugin and registers standalone executable launchers in your user binary path:

```bash
# Standard global symlink installation across all Antigravity surfaces
agyis install --global --symlink

# Or install from developer source tree
./agyis install --all-surfaces

# Optional: Enable Reverse Engineer Anything (REA) cleanroom tooling
agyis install --global --symlink --experimental-rea
```

#### What `agyis install` configures:
1. **Surfaces Registration**: Symlinks or copies the plugin into `~/.gemini/antigravity/plugins/agyis-harness`, `~/.gemini/antigravity-cli/plugins/`, and `~/.gemini/gemini-cli/plugins/`.
2. **Standalone Launchers**: Creates executable binary launchers for `agyis` and `psl` in `~/.local/bin` and `~/.gemini/antigravity/bin/`.
3. **Lifecycle Hooks**: Deploys `hooks.json` to register the 6 deterministic safety and verification hooks.
4. **Git State Hygiene**: Adds `.agents/archive/` and local state paths to `.git/info/exclude` to guarantee zero git pollution.

To uninstall cleanly without collateral damage:
```bash
agyis uninstall
```

### 2.2 The 3-Tier Runtime Compatibility Matrix
Agyis Harness audits host environments against the codified 3-tier runtime matrix defined in `harness/runtime/matrix.json`:

| Tier | Category | Minimum Spec | Probed Tools & Checks |
| :--- | :--- | :--- | :--- |
| **Tier 1** | **Languages & Packaging** | Python >= 3.12.0<br>Node.js >= 20.0.0 | `python3` (CPython >= 3.12, PEP 701 f-strings), `node` (ESM module hygiene), `uv` (fast hermetic Python), `pnpm` (fast package manager). |
| **Tier 2** | **Core SWE Toolchain** | Git >= 2.38.0<br>GitHub CLI >= 2.30.0 | `git` (safe worktrees, sparse checkout), `gh` (authenticated PR creation), `rg` (ripgrep >= 13.0), `fd` (fd-find >= 8.7). |
| **Tier 3** | **Mesh & Systems Host** | OpenSSH >= 8.9<br>Knot >= 1.0.0 | `ssh` (OpenSSH ControlMaster multiplexing), `knot` (mesh coordination). |

### 2.3 Diagnostic Engine (`agyis doctor`)
Run `agyis doctor` to perform a comprehensive audit of your workstation environment:

```bash
agyis doctor
```

Example output on a healthy workstation:
```text
======================================================================
 🩺 Agyis Harness: Workstation Runtime Diagnostic
======================================================================
 OS Family: ARCH | Host: desktop-anchor | Kernel: Linux 6.13.4-arch1
 Hermetic uv Python: /home/kuasha/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3
----------------------------------------------------------------------
 [PASS] uv                     >=0.1.0        -> /home/kuasha/.local/bin/uv (0.6.14)
 [WARN] python                 >=3.12.0       -> /home/kuasha/.pyenv/shims/python3 (3.14.7) ⚠️ pyenv shim active in PATH
 [PASS] node                   >=20.0.0       -> /usr/bin/node (22.13.1)
 [PASS] pnpm                   >=8.0.0        -> /usr/bin/pnpm (9.15.4)
 [PASS] git                    >=2.38.0       -> /usr/bin/git (2.48.1)
 [PASS] gh                     >=2.30.0       -> /usr/bin/gh (2.67.0)
 [PASS] rg                     >=13.0.0       -> /usr/bin/rg (14.1.1)
 [PASS] fd                     >=8.7.0        -> /usr/bin/fd (10.2.0)
 [PASS] ssh                    >=8.9.0        -> /usr/bin/ssh (OpenSSH_9.9p1)
 [PASS] knot                   >=1.0.0        -> /home/kuasha/.local/bin/knot (1.2.0)
 [PASS] Database Port (5432)   TCP Listen     -> Available
----------------------------------------------------------------------
 Summary: 10 OK | 1 Warnings | 0 Outdated | 0 Missing
 ✔ Fast-path diagnostic completed in 0.042s (Benchmark Invariant <1.0s).
```

#### Diagnostic Capabilities & Invariants:
1. **Pyenv / Conda Shim Hijacking Detection**:  
   If an active pyenv shim (`~/.pyenv/shims/python3`) or conda environment intercepts `python3`, `agyis doctor` emits a non-blocking warning (`[WARN] ... ⚠️ pyenv shim active in PATH`). The command-safety hook ensures that inline agent scripts automatically bind to certified hermetic Python >= 3.12 from `uv`.
2. **Hermetic uv Python Auto-Discovery**:  
   Scans `~/.local/share/uv/python/` for installed CPython versions (`cpython-3.12.*`), confirming runtime injection readiness.
3. **Database Port Collision Probing (Port 5432)**:  
   Detects if PostgreSQL port 5432 is occupied by foreign Docker containers (e.g., `jasper_dev_postgres`) or background system services, warning the operator before spinning up conflicting database test containers. Remediation script:
   ```bash
   python3 harness/skills/db-ops/scripts/detect_port_collision.py --find-free --rebind --env .env
   ```
4. **Fast-Path Invariant**:  
   Standard `agyis doctor` completes in **<0.05 seconds**. Missing optional tools (such as REA) add 0 warnings to standard output, preserving sub-second benchmark invariants.
5. **Opt-in REA Provider Audit (`--experimental-rea`)**:  
   Deeply probes Reverse Engineer Anything (REA 6.5.0), disassembler providers (Ghidra headless analyzer, Hopper launcher, IDA adapter, JADX), JDK 21+ discovery ladder, and MCP tool registrations:
   ```bash
   agyis doctor --experimental-rea
   ```

### 2.4 Zero-Sudo User-Space Auto-Healing (`agyis doctor --heal`)
When runtimes or tools are missing, `agyis doctor --heal` executes safe, user-space auto-healing with **zero sudo and zero system pollution**:

```bash
agyis doctor --heal
```

#### Auto-Healing Sequence:
- **Missing Python >= 3.12**: Uses `uv` to download and install a certified user-space CPython 3.12 build:
  ```bash
  uv python install 3.12
  ```
- **Missing `uv` or `pnpm`**: Downloads official standalone user-space binaries directly to `~/.local/bin`.
- **Combined with `--experimental-rea`**: Installs `rea-agents` package into a dedicated uv virtual environment and configures the `rea` stdio MCP server in `~/.gemini/config/mcp_config.json`.

---

## 3. Turnkey Workspace Onboarding (`agyis onboard`)

### 3.1 Overview: Eliminating Manual Onboarding Drift
Historically, onboarding a new or existing repository to the Agyis runtime required a complex, error-prone 7-step manual sequence (checking git status, stashing WIP, creating branches, running `agyis harmonize`, manually copying skills, editing `.git/info/exclude`, running tests, and opening PRs).

`agyis onboard` consolidates all 7 steps into a single, idempotent, turnkey CLI command equipped with automatic git topology probing, safety gates, build cache purging, and single-source skill deduplication:

```bash
# Turnkey onboarding of the current workspace
agyis onboard

# Onboard a target repository with specific language and role presets
agyis onboard /path/to/repo --lang python --role backend

# Onboard with dedicated branch isolation and automated Pull Request creation
agyis onboard --create-branch --pr
```

### 3.2 Full Flag Palette & Semantics

| Flag / Option | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `path` | Positional | Current dir (`.`) | Target workspace repository directory. |
| `--lang`, `--stack`, `-s` | String | Auto-detected | Language runtime preset: `typescript`, `node`, `javascript`, `python`, `rust`, `go`, `systems`, `shell`, `auto`. |
| `--role`, `-r` | Choice | None | Architectural role preset: `backend`, `frontend`, `fullstack`, `cli`, `library`, `mobile`, `desktop_gui`, `media`, `audio`, `infra`. |
| `--skills` | String | None | Comma-separated list of explicit modular skills to provision (e.g. `--skills db-ops,git-worktree-ops`). Overrides preset inference. |
| `--subproject` | String | None | Scoped subproject relative path for monorepos (e.g. `--subproject services/billing`). |
| `--create-branch [name]` | String | None (`chore/agyis-harness-onboarding`) | Creates and checks out an isolated onboarding branch before making any file modifications. |
| `--allow-dirty` | Flag | `False` | Safety gate: allows onboarding on a dirty working tree by automatically generating a safety patch snapshot. |
| `--purge-caches` | Flag | `True` | Automatically purges stale build caches (`.next`, `.turbo`, `node_modules/.cache`) up to depth 3 before verification. |
| `--no-cache-purge` | Flag | `False` | Disables automated build cache purging. |
| `--prune-legacy` | Flag | `True` | Safely archives legacy `.agent/` directories to tar.gz and manifest before deleting them. |
| `--no-prune` | Flag | `False` | Disables deletion of legacy `.agent/` directory. |
| `--pr`, `--open-pr` | Flag | `False` | Opens a GitHub Pull Request via `gh pr create` upon successful test verification. |
| `--upstream-remote` | String | Auto-detected | Explicit upstream remote name (e.g. `upstream`, `canonical`, `purrfectsoft`). |
| `--base-branch` | String | Auto-detected | Explicit base branch to target (defaults to default branch or active branch). |
| `--dry-run` | Flag | `False` | Simulates all onboarding actions without modifying disk files or git branches. |
| `--json` | Flag | `False` | Outputs machine-readable structured JSON report. |
| `--experimental-rea` | Flag | `False` | Provisions Reverse Engineer Anything (REA) cleanroom specifications and ledgers. |

### 3.3 Critical Safety Gates & Operational Invariants

#### 1. Harness Host Repository Protection
`agyis onboard` automatically detects if it is executed within the Agyis harness development repository itself (`is_harness_host: true`). It gracefully skips self-referential onboarding and exits with code 0:
```text
💡 Notice: Workspace is the Agyis harness host repository. Skipping self-referential onboarding.
```

#### 2. Dirty Working Tree Safety Gate & Patch Generation
Running automated onboarding on a repo with uncommitted changes risks data loss.
- **Default Behavior**: If uncommitted changes exist, `agyis onboard` immediately halts before making any modifications:
  ```text
  ✘ Error: Working tree has uncommitted changes. Stash/commit your changes or use --allow-dirty.
  ```
- **With `--allow-dirty`**: If the operator explicitly passes `--allow-dirty`, the engine captures a snapshot of all uncommitted work via `git diff HEAD` and writes it to:
  ```text
  <workspace>/.agents/artifacts/wip-safety-pre-onboard.patch
  ```
  It then adds `.agents/artifacts/` to `.git/info/exclude` and proceeds safely.

#### 3. Dedicated Branch Isolation (`--create-branch`)
To keep `main` or `develop` pristine, passing `--create-branch` automatically creates and checks out a new branch:
```bash
# Defaults to branch 'chore/agyis-harness-onboarding'
agyis onboard --create-branch

# Or specify a custom branch name
agyis onboard --create-branch feat/upgrade-harness-rc5
```

#### 4. Pre-Verification Build Cache Invalidation (`--purge-caches`)
Stale Next.js and Turborepo compilation caches frequently cause spurious TypeScript declaration errors (TS2307) during verification.
- `agyis onboard` automatically scans up to directory depth 3 in root and subproject folders.
- It safely unlinks `.next`, `.turbo`, and `node_modules/.cache` directories before verification.
- Symlinks are unlinked without recursively deleting target directories outside the workspace boundary.

#### 5. Single-Source Skill Deduplication
Early harness releases copied entire skill directories into `<repo>/.agents/skills/`. This caused skill shadowing and wasted ~4,500 prompt tokens per turn on duplicate instructions.
- `agyis onboard` computes SHA-256 cryptographic hashes for each workspace skill.
- If a skill in `.agents/skills/<name>` is identical to the global plugin skill in `~/.gemini/config/plugins/...`, the local copy is pruned.
- If the local copy contains unique customizations, it is preserved. Pruned duplicate skills are recorded in `skills_deduplicated`.

#### 6. Legacy `.agent/` Safety Archival & Deterministic 2-Step Pruning
When upgrading older repositories that used the legacy singular `.agent/` directory:
1. Calculates SHA-256 checksums of all legacy files.
2. Compresses the entire legacy directory into `.agents/archive/legacy-agent-backup-<timestamp>.tar.gz` alongside a `-manifest.json`.
3. Appends `.agents/archive/` to `.git/info/exclude`.
4. Executes a deterministic 2-step prune: `git rm -rf .agent` followed by `shutil.rmtree`.
5. Evaluates the strict invariant: `assert not legacy_agent_dir.exists()`.

#### 7. Automated PR Delivery (`--pr`)
When onboarding finishes and the repository's native test suite passes cleanly, passing `--pr` invokes `gh pr create` with a structured PR title and body targeting the detected upstream remote:
```bash
agyis onboard --lang typescript --role frontend --create-branch --pr
```

---

## 4. Fleet Upgrades & Synchronization

### 4.1 Consolidation of `rebase` and `update` Capabilities
During early release planning (RFCs in `rc4_rehydration_findings.md` §4 and Issue #63), independent subcommands named `agyis rebase` and `agyis update` were proposed for updating client repositories.

**Architectural Ground Truth**:
Neither `rebase` nor `update` exists as an independent CLI subcommand. Investigation across fleet upgrades demonstrated that updating a repository's harness configuration is fundamentally identical to brownfield onboarding. Consequently, all planned upgrade, cache invalidation, branch checkout, and PR delivery capabilities were **consolidated into `agyis onboard`**.

| Proposed Feature | Consolidated Capability in `agyis onboard` |
| :--- | :--- |
| Pre-verification build cache purge | `--purge-caches` (enabled by default; purges `.next`, `.turbo`) |
| Dedicated upgrade branch checkout | `--create-branch [name]` (e.g. `chore/upgrade-rc5`) |
| Remote fork/upstream topology probing | Built-in `GitTopologyProbe` in `onboard.py` |
| Safety snapshot of local uncommitted edits | `--allow-dirty` (writes `.agents/artifacts/wip-safety-pre-onboard.patch`) |
| Single-source skill deduplication | Built-in `enforce_single_source_skills` |
| Automated PR creation | `--pr` (invokes `gh pr create` upon verified test pass) |

### 4.2 Standard Fleet Upgrade Workflows

#### Workflow A: Upgrading an Existing Repository to `v1.0.0-rc5`
To upgrade any repository across your fleet:
```bash
cd /path/to/client-repo

# Run onboard with branch isolation, cache purging, and PR creation
agyis onboard . --purge-caches --create-branch chore/agyis-rc5-upgrade --pr
```

#### Workflow B: Refreshing Rules and Command Dictionaries
If you only want to refresh `AGENTS.md` rules with the latest empirical standards:
```bash
# Harmonize rules without touching other files
agyis harmonize .

# Or preview changes first
agyis harmonize . --dry-run
```

#### Workflow C: Synchronizing Modular Skills
To update workspace skills from the global plugin catalog:
```bash
# Synchronize skills and override existing templates
agyis skills --sync --override --workspace

# Prune redundant workspace skills shadowing global plugins
agyis skills --prune-duplicates --workspace
```

#### Workflow D: Upgrading Global Harness Installation
To upgrade the global Agyis harness toolchain on your workstation:
```bash
# If installed via uv tool
uv tool update agyis-harness

# If installed from source checkout
cd /home/kuasha/Dev/psl-agy-harness
git pull origin main
./agyis test
./agyis install --global --all-surfaces
```

---

## 5. Background Telemetry Sync Daemon (`agyis sync --service`)

### 5.1 Native Systemd User Service Management
Google Antigravity sessions generate empirical trajectories in local SQLite databases (`data/telemetry.db` or `~/.gemini/antigravity/conversations/*.db`). Synchronizing these sessions with the central PSL telemetry hub enables multi-device trajectory analysis and failure classification.

Historically, setting up the background watch daemon required manual shell redirection (`agyis sync --systemd > ~/.config/systemd/user/agyis-sync.service`) followed by manual `systemctl` commands. This pattern caused terminal hangs in non-interactive agent sessions and was prone to path corruption.

`v1.0.0-rc5` introduces **native systemd user service management** via `agyis sync --service`:

```bash
agyis sync --service [install | status | start | stop | uninstall]
```

### 5.2 Service Lifecycle Commands

#### 1. Install & Enable the Service
Installs the systemd unit file to `~/.config/systemd/user/agyis-sync.service`, reloads the user systemd daemon, and enables the service to start automatically on login:
```bash
agyis sync --service install
```

To configure a custom polling interval (default is 5.0 seconds):
```bash
agyis sync --service install --interval 10.0
```

#### 2. Query Service Status
Inspects whether the unit file is installed, whether the service is actively running, and prints diagnostic information:
```bash
agyis sync --service status
```
Output when active:
```text
● agyis-sync.service - Agyis Harness Background Telemetry Sync Daemon
     Loaded: loaded (/home/kuasha/.config/systemd/user/agyis-sync.service; enabled)
     Active: active (running) since Sun 2026-10-18 10:15:00 UTC; 2h 14min ago
```
Output in JSON mode (`--json`):
```json
{
  "service": "agyis-sync.service",
  "installed": true,
  "active": true,
  "status": "active",
  "path": "/home/kuasha/.config/systemd/user/agyis-sync.service"
}
```

#### 3. Start or Stop the Service
```bash
# Start background synchronization immediately
agyis sync --service start

# Stop background synchronization
agyis sync --service stop
```

#### 4. Clean Uninstallation
Stops the daemon, disables the unit, unlinks the unit file, and executes `daemon-reload`:
```bash
agyis sync --service uninstall
```

### 5.3 Headless / Container Fallback (`agyis sync --watch`)
In headless environments, containers (Docker), or platforms lacking a user DBus session where `systemctl --user` is unavailable, `agyis sync --service install` detects the absence of systemd and exits cleanly with guidance to use the foreground watch daemon:
```bash
# Run continuous foreground watch loop (e.g. inside Docker or tmux)
agyis sync --watch --interval 10.0
```

### 5.4 Hub Authentication & Bi-Directional Synchronization
Before synchronizing telemetry with the central hub, configure GitHub organization authentication:

```bash
# Authenticate using active GitHub CLI token
agyis auth login --gh --endpoint https://telemetry.purrfectsoft.com

# Perform manual bi-directional sync (push local, pull remote)
agyis sync

# Dry-run preview: check pending session count without network mutation
agyis sync --dry-run

# Pull fleet-wide telemetry authored by all developers (bypassing anti-echo filter)
agyis sync --pull --all-developers
```

---

## 6. End-User Troubleshooting & FAQ

| Symptom | Cause | Solution |
| :--- | :--- | :--- |
| `[WARN] python ... ⚠️ pyenv shim active in PATH` | Host `$PATH` points to a legacy pyenv shim (e.g. Python 3.10) | Run `agyis doctor --heal`. Agyis Harness lifecycle hooks automatically inject hermetic CPython >= 3.12 from `uv` during inline tool execution. |
| `Port 5432 collision: occupied by foreign container` | An existing Docker container (e.g. `jasper_dev_postgres`) is binding port 5432 | Run `python3 harness/skills/db-ops/scripts/detect_port_collision.py --find-free --rebind --env .env` to find a free port and rebind your configuration. |
| `✘ Error: Working tree has uncommitted changes` | `agyis onboard` aborted to protect your unstaged files | Commit or stash your changes, or pass `agyis onboard --allow-dirty` to generate an automated safety patch snapshot. |
| `TS2307: Cannot find module` during verification | Stale Next.js / Turborepo type caches lingering in `.next/types` | Re-run onboarding with cache purging: `agyis onboard --purge-caches`. |
| `Service 'agyis-sync.service' is not installed` | Systemd background sync daemon has not been set up | Run `agyis sync --service install` to install and enable the background daemon. |
| Stop event denied: `Execute active repository test suite` | Completion fence detected unverified code modifications | Run the active project test suite (`agyis test`, `pytest`, `npm test`, `cargo test`) and ensure exit code 0 before concluding the task. |
