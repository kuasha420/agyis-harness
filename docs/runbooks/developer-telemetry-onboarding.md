---
title: PSL Developer Onboarding & Telemetry Sync Runbook
description: Step-by-step operational runbook for new PSL team members to install agyis-harness, authenticate with GitHub, harvest existing Antigravity transcripts, and synchronize full history to the telemetry hub.
version: 1.0.1
last_updated: 2026-10-06
target_audience: [developer, onboarding]
related_adrs: [ADR-014, ADR-015, ADR-030]
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# 🚀 PSL Developer Onboarding: Telemetry Setup & History Sync Runbook

This guide walks new members of **Purrfect Software Laboratories (PSL)** through setting up `agyis-harness`, registering the global Antigravity toolchain, ingesting local historical agent sessions, and synchronizing telemetry to the centralized fleet hub at **`https://psl-harness.infra.purrfecthq.com`**.

---

## 1. Prerequisites & Access Requirements

Before starting, verify your workstation has the following prerequisites:

| Requirement | Minimum Version | Verification Command | Notes |
| :--- | :--- | :--- | :--- |
| **Python** | 3.12+ (CPython >= 3.12.0) | `python3 --version` | Standard library only; zero third-party `pip` packages required for telemetry sync (Tier 1 runtime matrix requirement). |
| **Git** | 2.38+ | `git --version` | Standard git toolchain with safe worktrees and sparse-checkout (Tier 2 matrix requirement). |
| **GitHub CLI (`gh`)** | 2.30+ | `gh auth status` | Must be logged into an account that is a member of the **`purrfectsoft`** GitHub organization. |
| **Google Antigravity** | Any active version | `ls ~/.gemini/antigravity/brain/` | Your local historical agent transcripts are stored here. |
| **Network Access** | Outbound HTTPS | `curl -s https://psl-harness.infra.purrfecthq.com/api/v1/health` | Expected response: `{"status":"ok","version":"1.0.0","database":"connected"}`. |

> [!IMPORTANT]
> **GitHub Organization Membership & Scope**: Gateway access requires active membership in the `purrfectsoft` GitHub organization. Ensure your `gh` token includes the `read:org` scope:
> ```bash
> gh auth refresh -h github.com -s read:org
> ```

---

## 2. Fast-Path Quickstart (5 Minutes)

Run these sequential steps in your terminal to complete onboarding and synchronize your full session history.

### Step 1: Clone the Repository
```bash
# Clone to your standard Dev directory
git clone https://github.com/kuasha420/agyis-harness.git ~/Dev/agyis-harness
cd ~/Dev/agyis-harness
```

### Step 2: Install Global Toolchain & Plugin
```bash
./agyis install --global
```
- **What this does**:
  1. Registers and symlinks the harness plugin to `~/.gemini/config/plugins/agyis-harness/`.
  2. Installs the standalone executable to `~/.local/bin/agyis` and backward-compatible alias `~/.local/bin/psl` (`chmod 0755`), ensuring `agyis` is available everywhere in `$PATH`.
  3. Registers the harness plugin so Google Antigravity discovers all lifecycle hooks, modular skills, and specialist subagents globally. *(To symlink skills directly into a local workspace's `.agents/skills/`, run `agyis skills --sync`).*
- **Verification**:
  ```bash
  which agyis
  # Expected: ~/.local/bin/agyis or /home/<user>/.local/bin/agyis
  ```
  *(If `command not found: agyis`, ensure `~/.local/bin` is in your `$PATH` by adding `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc` or `~/.zshrc`).*

### Step 3: Authenticate via GitHub CLI
Authenticate against the centralized telemetry hub with zero interactive copy-pasting:
```bash
agyis auth login --gh --endpoint https://psl-harness.infra.purrfecthq.com
```
- **Verification**:
  ```bash
  agyis auth status
  ```
  *(Confirms `Authenticated: Yes`, username, and active organization membership).*

### Step 4: Harvest Existing Local History
Ingest all historical Antigravity transcripts stored on your workstation:
```bash
agyis audit extract
```
- **What this does**:
  - Automatically crawls `~/.gemini/antigravity/brain/*/` for all session transcripts.
  - Parses steps, tool calls, thinking blocks, errors, and human intervention points.
  - Stores harvested telemetry in local SQLite (`data/telemetry.db`).

### Step 5: Synchronize to the Centralized Hub
First preview your pending sync payload:
```bash
# Dry-run validation (safe inspection)
agyis sync --dry-run
```
Then execute the live synchronization:
```bash
agyis sync
```
- **What this does**:
  - Partitions sessions into transactional chunks ($\le 10$ sessions or $\le 2,500$ steps per batch) to guarantee payloads pass reverse proxies without `HTTP 413` errors.
  - Applies client-side sanitization and credential scrubbing before transmission.
  - Updates `remote_synced_at` timestamps locally upon each successful batch transmission.

---

## 3. Privacy, Security & Denylist Controls

PSL enforces strict, non-negotiable security boundaries built directly into the client transport:

1. **Pre-Transmission Scrubbing**:
   - `strip_secrets()` automatically strips GitHub tokens, API keys, Bearer auth headers, passwords, SSH/PEM keys, and database connection strings before JSON serialization.
   - `anonymize_paths()` anonymizes absolute home directory paths (`/home/<username>/...`).
2. **Workspace Denylists**:
   To permanently prevent proprietary client repositories or personal workspaces from being harvested or uploaded:
   Add patterns to your global configuration file (`~/.config/psl/config.json`):
   ```json
   {
     "endpoint": "https://psl-harness.infra.purrfecthq.com",
     "denylist": [
       "*/confidential-client/*",
       "*/personal-finances/*",
       "*/sandbox-temp/*"
     ]
   }
   ```
3. **Interactive & Selective Sync**:
   To inspect sessions before pushing:
   ```bash
   agyis sync --interactive
   ```
   To push without pulling peer sessions:
   ```bash
   agyis sync --push
   ```

---

## 4. Workstation Health & Verification

After completing your initial sync, run harness diagnostics to verify local lifecycle hooks and subagent configurations:

```bash
# 1. Run environment and hook sanity diagnostics
agyis doctor

# 2. View local harness overview and telemetry count
agyis status
```

---

## 5. Troubleshooting & FAQ

### Q1: `agyis auth login` fails with `Error 403: User is not an authorized member of the organization`
- **Cause**: Your GitHub account is not an active member of `purrfectsoft` or SSO authorization is pending.
- **Solution**:
  1. Check organization membership: `gh api user/orgs --jq '.[].login'`.
  2. If missing, request an invitation from the engineering team lead.
  3. Re-authenticate: `gh auth refresh -h github.com -s read:org`.

### Q2: I don't use GitHub CLI (`gh`). How do I authenticate?
- **Solution**: Pass your Personal Access Token directly via stdin or CLI argument:
  ```bash
  # Via prompt:
  agyis auth login --endpoint https://psl-harness.infra.purrfecthq.com

  # Via pipe:
  echo "YOUR_GITHUB_PAT" | agyis auth login --endpoint https://psl-harness.infra.purrfecthq.com
  ```

### Q3: `agyis sync` fails with `FileNotFoundError` or reports `0 sessions pushed`
- **Cause**: Transcripts have not been extracted into SQLite yet. (Under ADR-030 path resolution, if `data/telemetry.db` has not been initialized yet, `agyis sync` raises an explicit `FileNotFoundError` to prevent phantom empty database creation; if an empty database exists, it reports `0 sessions pushed`).
- **Solution**:
  Run `agyis audit extract` first to parse transcripts into `data/telemetry.db`, then re-run `agyis sync`.

### Q4: How do I sync only a single specific session?
- **Solution**:
  ```bash
  agyis sync --session-id <conversation-id>
  ```
