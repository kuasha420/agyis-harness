---
title: Knot Mesh Fleet Update & Telemetry Sync Runbook
description: Comprehensive operational runbook for Developers, AI Subagents, and Knot Mesh Strands to update psl-agy-harness, deploy global binaries, authenticate via GitHub CLI, and execute chunked telemetry synchronization.
version: 1.0.1
last_updated: 2026-10-06
target_audience: [developer, ai_agent, knot_mesh]
related_adrs: [ADR-014, ADR-015, ADR-027, ADR-030]
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Purrfect Software Limited (PSL) -->

# 🌐 Knot Mesh Fleet Update & Telemetry Sync Runbook

This runbook defines the canonical standard operating procedure (SOP) for updating the `psl-agy-harness` toolchain, deploying global standalone executables, authenticating organization credentials, and performing resilient telemetry synchronization across the physical Knot mesh fleet (`@desktop`, `@laptop`, `@steamdeck`) and the internal development gateway (`psl-harness.infra.purrfecthq.com`).

---

## 1. Architectural Foundations & Invariants

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              FLEET TOPOLOGY & ACCESS MODES                             │
├─────────────────┬────────────────────────────┬─────────────────────────────────────────┤
│ Tier / Node     │ Role                       │ Primary Responsibilities                │
├─────────────────┼────────────────────────────┼─────────────────────────────────────────┤
│ `@desktop`      │ Anchor Architect           │ Ingestion authority, primary storage,   │
│                 │ (Coordination Lead)        │ batch dispatch, telemetry gateway dev   │
├─────────────────┼────────────────────────────┼─────────────────────────────────────────┤
│ `@laptop`       │ Compute Worker             │ CUDA offload, deep forensic mining,     │
│                 │ (RTX 3050 CUDA)            │ local transcripts harvesting            │
├─────────────────┼────────────────────────────┼─────────────────────────────────────────┤
│ `@steamdeck`    │ Handheld Controller        │ Portable field node, low-power testbed, │
│                 │ (Zen2 / RDNA2 APU)         │ local session telemetry extraction      │
├─────────────────┼────────────────────────────┼─────────────────────────────────────────┤
│ Internal Hub    │ Telemetry Gateway          │ Starlette ASGI, CloudPanel Nginx proxy, │
│ (`psl-harness`) │ (Federation Sink)          │ GitHub Org auth caching (300s TTL)      │
│                 │                            │ `psl-harness.infra.purrfecthq.com`      │
└─────────────────┴────────────────────────────┴─────────────────────────────────────────┘
```

### Deterministic Invariants (ADR-030 Hardening)
1. **Zero-CWD Probing Invariant**: Database path resolution strictly ignores `$PWD/data/telemetry.db` to prevent silent database proliferation when commands are invoked from arbitrary directories.
2. **Chunked Batch Invariant**: Telemetry payloads exceeding 10 sessions or 2,500 steps are partitioned into client-side chunks to guarantee payloads never trigger `HTTP 413 Payload Too Large` through reverse proxies.
3. **Per-Batch Transactional Commits**: SQLite marks `remote_synced_at` and commits per batch upon HTTP 200, guaranteeing that network interruptions during multi-batch pushes do not rollback previously synced sessions.
4. **Standalone Executable Delivery**: `psl install --global` deploys both the Antigravity plugin and a standalone user executable `~/.local/bin/psl` (`0o755`), ensuring `psl` is available everywhere in `$PATH`.
5. **Zero-Input Credential Lifting**: `psl auth login --gh` executes `gh auth token` via CPython stdlib `subprocess` without interactive prompts or copy-pasted tokens.

---

## 2. Track 1: Developer Interactive Workflow (Local Workstation)

For human operators updating their current development machine.

### Step 1: Reconcile Codebase
```bash
cd ~/Dev/psl-agy-harness
git checkout main
git pull origin main
```

### Step 2: Install Global Plugin & Executable
```bash
./psl install --global
```
- **What this does**:
  - Symlinks package to `~/.gemini/config/plugins/psl-agy-harness/`.
  - Installs executable launcher to `~/.local/bin/psl` with `0o755` permissions.
- **Verification**:
  ```bash
  which psl
  # Expected: /home/<user>/.local/bin/psl
  ```

### Step 3: Zero-Friction GitHub Authentication
Authenticate against the internal development gateway using your GitHub organization credentials:

```bash
# Connect to internal development gateway via GitHub CLI token
psl auth login --gh --endpoint https://psl-harness.infra.purrfecthq.com
```

- **Verify status**:
  ```bash
  psl auth status
  ```
  *(Confirms `Authenticated: Yes`, active organization membership, and gateway endpoint).*

#### Workspace-Scoped Endpoints (Optional)
To point a specific project workspace to a local or alternative gateway without modifying your global user configuration:
```bash
cd /path/to/my-project
psl auth login --endpoint http://127.0.0.1:8000 --workspace
```
*(Writes `<project>/.psl/config.json`, which takes precedence over `~/.config/psl/config.json`).*

### Step 4: Harvest & Synchronize Telemetry
```bash
# 1. Harvest local transcripts into SQLite
psl audit extract

# 2. Preview pending sessions (optional dry-run)
psl sync --dry-run

# 3. Synchronize with chunked batching
psl sync
```

### Step 5: Sanity Diagnostics
```bash
# Verify 3-tier runtime matrix
psl doctor

# Confirm active hooks, registered subagents, and database stats
psl status
```

---

## 3. Track 2: Autonomous AI Agent Protocol (Antigravity & Ladder Subagents)

For autonomous agents, background daemons, or CI/CD pipelines executing without an interactive TTY.

### Protocol Guidelines for AI Agents:
- **Always use machine-readable output**: Append `--json` to inspect structured payloads.
- **Always specify explicit paths**: When invoking across worktrees, pass `--db <path>` explicitly.
- **Never poll or sleep in loops**: Await process exit codes; parse JSON stderr on failure.

### Command Palette for AI Execution:

```bash
# 1. Non-interactive dry-run audit
psl sync --dry-run --json

# 2. Machine-readable synchronization
psl sync --json

# 3. Targeted database push
psl sync --db /home/kuasha/Dev/psl-agy-harness/data/telemetry.db --json

# 4. Auth status check
psl auth status --json

# 5. Non-interactive auth login with explicit token
echo "$GITHUB_TOKEN" | psl auth login --endpoint https://psl-harness.infra.purrfecthq.com --json
```

### JSON Schema Verification Reference:
```json
// Successful sync response schema:
{
  "status": "success",
  "push": {
    "status": "success",
    "sessions_pushed": 12,
    "steps_pushed": 3410,
    "tool_calls_pushed": 482,
    "user_interventions_pushed": 18,
    "synced_at": "2026-10-06T08:00:00.000000+00:00",
    "dry_run": false
  },
  "pull": {
    "status": "success",
    "sessions_inserted": 0,
    "steps_inserted": 0
  }
}
```

---

## 4. Track 3: Knot Mesh Multi-Node Orchestration

For orchestrating multi-node synchronizations across physical hardware strands (`@desktop`, `@laptop`, `@steamdeck`).

### Option A: Zero-Token Mesh Orchestration via `knot exec`

Execute the synchronized update loop across strands with **0 token burn**:

```bash
# 1. Synchronize the CUDA Compute Worker (@laptop)
knot exec laptop '
  set -e
  cd ~/Dev/psl-agy-harness
  git checkout main && git pull origin main
  ./psl install --global
  psl auth login --gh --endpoint https://psl-harness.infra.purrfecthq.com
  psl audit extract
  psl sync
  psl status
'

# 2. Synchronize the Handheld Testbed (@steamdeck)
knot exec steamdeck '
  set -e
  cd ~/Dev/psl-agy-harness
  git checkout main && git pull origin main
  ./psl install --global
  psl auth login --gh --endpoint https://psl-harness.infra.purrfecthq.com
  psl audit extract
  psl sync
  psl status
'
```

### Option B: Parallel Fleet Broadcast
```bash
# Broadcast git reconciliation across all online strands simultaneously
knot exec --all "cd ~/Dev/psl-agy-harness && git pull origin main && ./psl install --global && psl sync"
```

### Option C: OpenSSH Multiplexed Harness Execution (ADR-027)
If invoking via the PSL remote operations subsystem:

```bash
# Fast multiplexed SSH check (<100ms via ControlMaster)
python3 -m harness.cli remote exec laptop "psl status"

# Run remote health triage
python3 -m harness.cli remote triage laptop
```

---

## 5. Configuration & Environment Variable Reference

The harness evaluates configuration in a strict 5-tier hierarchy.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        CONFIGURATION HIERARCHY                         │
│                                                                        │
│   1. CLI Argument Flags (--db, --endpoint, --token)                    │
│      ▲                                                                 │
│   2. Environment Variables (PSL_TELEMETRY_DB, PSL_SYNC_ENDPOINT)       │
│      ▲                                                                 │
│   3. Workspace Config (<workspace>/.psl/config.json)                   │
│      ▲                                                                 │
│   4. User Global Config (~/.config/psl/config.json)                    │
│      ▲                                                                 │
│   5. Production Default Hardcoded Constants                            │
└────────────────────────────────────────────────────────────────────────┘
```

| Variable / Flag | Default Value | Description |
|---|---|---|
| `PSL_SYNC_ENDPOINT` | `https://psl-harness.infra.purrfecthq.com` (prod) / `http://localhost:8000` (local) | Remote gateway endpoint URL |
| `PSL_TELEMETRY_DB` | `REPO_ROOT/data/telemetry.db` | Explicit SQLite database path override |
| `PSL_DATA_DIR` | `~/.local/share/psl` | XDG data directory for databases |
| `PSL_CONFIG_DIR` | `~/.config/psl` | XDG configuration directory |
| `PSL_BIN_DIR` | `~/.local/bin` | Target directory for global `psl` executable |
| `PSL_RETRY_BACKOFF`| `1.0` | Initial backoff seconds for transient 5xx retries |
| `--workspace` / `-w`| `False` | Scopes config write to `<workspace>/.psl/config.json` |
| `--global` / `-g` | `True` | Scopes config write to user `~/.config/psl/` |
| `--gh` | `False` | Lifts PAT token automatically from `gh auth token` |

---

## 6. Diagnostic Troubleshooting & Auto-Healing

### Issue 1: `Sync error: HTTP Error 413: Request Entity Too Large`
- **Cause**: Outdated client sending monolithic payload (>20MB) to Nginx reverse proxy.
- **Remedy**:
  1. Verify commit `23fe402` or later is checked out: `git log -n 1 --oneline`.
  2. Pull `main` and execute `psl sync`. The client will automatically chunk into $\le 10$ sessions or $\le 2,500$ steps.

### Issue 2: `FileNotFoundError: Telemetry database not found at ...`
- **Cause**: `psl sync` or `psl sync --push` executed outside repo checkout where no database has been created yet.
- **Remedy**:
  1. Extract local Antigravity sessions first: `psl audit extract`.
  2. Or pass explicit path: `psl sync --db /path/to/telemetry.db`.

### Issue 3: `Error 403: User is not an authorized member of the organization`
- **Cause**: The GitHub PAT does not belong to an active member of `purrfectsoft` organization.
- **Remedy**:
  1. Confirm your GitHub user is part of the org: `gh api user/orgs --jq '.[].login'`.
  2. Ensure the PAT has `read:org` scope or is generated with SSO authorization.

### Issue 4: `command not found: psl`
- **Cause**: `~/.local/bin` is not present in `$PATH`.
- **Remedy**:
  Add `~/.local/bin` to your shell profile:
  ```bash
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
  source ~/.bashrc
  ```
