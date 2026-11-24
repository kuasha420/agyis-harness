---
title: Telemetry Setup, Background Daemon & Fleet Sync Runbook
description: Human operator runbook for installing agyis-harness globally, optional self-hosted telemetry hub authentication, background sync daemon management, and multi-device SSH/fleet verification.
version: 2.1.0
last_updated: 2026-11-25
target_audience: [developer, operator]
related_adrs: [ADR-014, ADR-015, ADR-027, ADR-030]
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Telemetry Setup, Background Daemon & Fleet Sync Runbook

This human operator runbook covers workstation installation, local transcript harvesting, optional self-hosted telemetry hub authentication, background daemon setup, and multi-device fleet verification for `agyis-harness`.

> **Autonomous Agent Reference**: Non-interactive `--json` agent execution loops and SQLite WAL/watermark invariants live in [`telemetry-sync`](../../harness/skills/telemetry-sync/SKILL.md) and [`remote-ops`](../../harness/skills/remote-ops/SKILL.md). External multi-node mesh tooling (`knot-mesh`) is maintained separately at `gh:kuasha420/knot-mesh` and is not required for standalone `agyis` telemetry or SSH operations.

---

## 1. Prerequisites & Global Installation

Standalone local telemetry (`agyis audit extract` and `agyis audit`) works completely offline with zero remote server or GitHub organization setup. Configure hub credentials only if you operate a self-hosted or team telemetry gateway:

| Requirement | Minimum Version | Verification Command | Notes |
| :--- | :--- | :--- | :--- |
| **Python** | CPython >= 3.12 | `python3 --version` | Standard library only; zero external `pip` dependencies required. |
| **Git** | 2.38+ | `git --version` | Worktree and sparse-checkout support. |
| **GitHub CLI (`gh`)** *(Optional)* | 2.30+ | `gh auth status` | Optional; needed only if your self-hosted telemetry hub gates access via GitHub org `read:org`. |
| **Antigravity Transcripts** | Active install | `ls ~/.gemini/antigravity/brain/` | Local conversation artifacts live here. |
| **Hub Reachability** *(Optional)* | Outbound HTTPS | `curl -sS https://<your-telemetry-hub>/api/v1/health` | Expected status: `{"status":"ok",...}` when running a remote hub. |

If your optional team telemetry hub requires GitHub org verification, refresh scopes first:

```bash
gh auth refresh -h github.com -s read:org
```

Clone the repository and register the global plugin and standalone launchers (`~/.local/bin/agyis` and legacy alias `~/.local/bin/psl`):

```bash
git clone https://github.com/kuasha420/agyis-harness.git /path/to/agyis-harness
cd /path/to/agyis-harness
./agyis install --global --wheel
which agyis
```

*(If `agyis` is missing from `$PATH`, add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc` or `~/.zshrc`.)*

---

## 2. Optional Self-Hosted Hub Auth, Privacy & Denylists

Skip this section if you only run local SQLite audits (`agyis audit`). When syncing across workstations through a self-hosted or team telemetry hub (remote endpoints must use `https://`; `http://` is restricted to loopback `localhost` / `127.0.0.1` dev hubs), authenticate once via your GitHub CLI session (or pass a PAT over stdin in headless environments):

```bash
agyis auth login --gh --endpoint https://<your-telemetry-hub>
agyis auth status
```

To target a local loopback development hub for a single repository without modifying global user config:

```bash
cd /path/to/<project-repo>
agyis auth login --endpoint http://127.0.0.1:8000 --workspace
```

*(Workspace config `<project>/.agyis/config.json` overrides `~/.config/agyis/config.json`.)*

### Client-Side Sanitization & Denylist Filtering

Before any session leaves your workstation, `harness/telemetry/redaction.py` strips tokens, credentials, and private home paths. To exclude confidential client or personal directories completely, add glob patterns to `~/.config/agyis/config.json`:

```json
{
  "endpoint": "https://<your-telemetry-hub>",
  "denylist": [
    "*/<confidential-client>/*",
    "*/personal-finances/*",
    "*/sandbox-temp/*"
  ]
}
```

---

## 3. Harvesting & Syncing Local Telemetry

Ingest local Antigravity transcripts into `data/telemetry.db` (`AGYIS_TELEMETRY_DB`), preview the payload, and push in reverse-proxy-safe batches ($\le 10$ sessions or $\le 2,500$ steps per HTTP chunk):

```bash
# 1. Harvest local transcripts into SQLite
agyis audit extract

# 2. Validate credentials and pending push/pull counts without mutating remote state
agyis sync --dry-run

# 3. Execute bi-directional sync (pushes local pending sessions, then pulls remote deltas)
agyis sync
```

Common selective flags for operators:

```bash
agyis sync --push                                  # Push local sessions only
agyis sync --pull --developer <developer-handle>   # Pull your sessions from other workstations
agyis sync --pull --all --since 2026-01-01T00:00:00Z # Pull fleet corpus delta from timestamp
agyis sync --interactive                           # Inspect sessions interactively before upload
agyis sync --session-id <conversation-id>          # Sync a single conversation ID
```

---

## 4. Background Sync Daemon (`agyis sync --service`)

On Linux workstations with systemd user sessions, enable automated background synchronization instead of running `agyis sync` manually:

```bash
agyis sync --service install    # Writes ~/.config/systemd/user/agyis-sync.service and enables it
agyis sync --service start      # Starts the background sync unit
agyis sync --service status     # Shows service health and recent logs (--json supported)
agyis sync --service stop       # Stops the daemon
agyis sync --service uninstall  # Stops, disables, and removes the unit file
```

For non-systemd environments (containers, macOS, or headless shells without D-Bus), emit a unit template or run a foreground watch loop:

```bash
agyis sync --systemd
agyis sync --watch --interval 10.0
```

> **SSH / tmux Systemd Tip**: If `--service status` reports `Failed to connect to bus`, export `XDG_RUNTIME_DIR="/run/user/$(id -u)"` and re-run.

---

## 5. Multi-Device Fleet Sync Verification

When syncing across multiple workstations, update each node and verify its telemetry & harness health remotely over ControlMaster SSH (`ADR-027`):

```bash
# Check and sync a specific remote workstation via ControlMaster SSH (ADR-027)
agyis remote exec <target-node> "cd /path/to/agyis-harness && git pull origin main && ./agyis install --global --wheel && agyis sync"
agyis remote exec <target-node> "agyis status"
agyis remote triage <target-node>

# Optional: if using external knot-mesh (gh:kuasha420/knot-mesh), broadcast across nodes:
# knot exec --all "cd /path/to/agyis-harness && git pull origin main && ./agyis install --global --wheel && agyis sync"
```

Confirm workstation readiness locally after syncing:

```bash
agyis doctor   # Audits 3-tier runtime matrix, 8 hook runner targets & port 5432 collisions
agyis status   # Displays harness readiness, active hooks, attention horizon & telemetry stats
```

---

## 6. Configuration Precedence & Environment Overrides

Settings resolve in strict 5-tier order (CLI flags override environment variables, which override workspace `.agyis/config.json`, user `~/.config/agyis/config.json`, and production defaults):

| Environment Variable | Legacy Fallback | Purpose |
| :--- | :--- | :--- |
| `AGYIS_SYNC_ENDPOINT` | `PSL_SYNC_ENDPOINT` | Self-hosted telemetry hub HTTPS URL (`https://<your-telemetry-hub>`) |
| `AGYIS_TELEMETRY_DB` | `PSL_TELEMETRY_DB` | Explicit SQLite database path (zero-CWD probing per ADR-030) |
| `AGYIS_DATA_DIR` | `PSL_DATA_DIR` | XDG data directory override (default `~/.local/share/agyis`) |
| `AGYIS_CONFIG_DIR` | `PSL_CONFIG_DIR` | XDG configuration directory (default `~/.config/agyis`) |
| `AGYIS_HARNESS_STATE_DIR` | `PSL_HARNESS_STATE_DIR` | Runtime hook state override (default `/tmp/agyis_harness_state_{uid}`) |
| `PSL_RETRY_BACKOFF` | — | Initial backoff seconds for transient 502/503/504 retries (`1.0`) |

---

## 7. Operator Troubleshooting & Verification Checklist

| Symptom | Cause | Resolution |
| :--- | :--- | :--- |
| `HTTP 401: Unauthorized` | GitHub PAT missing or expired | Run `agyis auth login --gh --endpoint https://<your-telemetry-hub>` |
| `HTTP 403: Forbidden` | Account lacks configured hub org membership or `read:org` scope | Verify org membership via `gh api user/orgs --jq '.[].login'` and run `gh auth refresh -h github.com -s read:org` |
| `FileNotFoundError` / `0 sessions pushed` | Local SQLite DB has not been populated yet | Run `agyis audit extract` before `agyis sync` |
| `HTTP 413: Request Entity Too Large` | Legacy unchunked client | Pull latest `main` and re-run `./agyis install --global --wheel` |
| `database is locked` | Concurrent write outside WAL busy timeout | Wait briefly and retry; WAL mode is managed automatically |
| Local DB / Prisma `P1000` warning in `agyis doctor` | Port `5432` occupied by a foreign container | See [`repo-onboarding.md`](repo-onboarding.md#6-database-port-5432-collision-check-prisma-p1000) |

### Verification Checklist
- [ ] `agyis auth status` confirms active authentication against your self-hosted/team hub (if using remote sync).
- [ ] `agyis sync --dry-run` connects cleanly and previews pending counts without error (if using remote sync).
- [ ] `agyis sync --service status` (or foreground `--watch`) confirms active synchronization.
- [ ] `agyis doctor` and `agyis status` pass cleanly on each synced workstation.
