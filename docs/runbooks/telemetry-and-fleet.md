---
title: Telemetry Setup, Background Daemon & Fleet Sync Runbook
description: Human operator runbook for installing agyis-harness globally, authenticating to the telemetry hub, managing the background sync daemon, and verifying multi-device Knot mesh sync.
version: 2.0.0
last_updated: 2026-11-11
target_audience: [developer, operator]
related_adrs: [ADR-014, ADR-015, ADR-027, ADR-030]
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Telemetry Setup, Background Daemon & Fleet Sync Runbook

This human operator runbook covers workstation installation, telemetry hub authentication, local transcript harvesting, background daemon setup, and multi-device fleet verification for `agyis-harness`.

> **Autonomous Agent Reference**: Non-interactive `--json` agent execution loops, SQLite WAL/watermark invariants, and low-level SSH/Tailscale/rsync mesh procedures live in the [`telemetry-sync`](../../harness/skills/telemetry-sync/SKILL.md) and [`mesh-ops`](../../harness/skills/mesh-ops/SKILL.md) skills rather than this guide.

---

## 1. Prerequisites & Global Installation

Verify workstation requirements before synchronizing telemetry:

| Requirement | Minimum Version | Verification Command | Notes |
| :--- | :--- | :--- | :--- |
| **Python** | CPython >= 3.12 | `python3 --version` | Standard library only; zero external `pip` dependencies required. |
| **Git** | 2.38+ | `git --version` | Worktree and sparse-checkout support. |
| **GitHub CLI (`gh`)** | 2.30+ | `gh auth status` | Must belong to `<github-org>` with `read:org` scope. |
| **Antigravity Transcripts** | Active install | `ls ~/.gemini/antigravity/brain/` | Local conversation artifacts live here. |
| **Hub Reachability** | Outbound HTTPS | `curl -sS <telemetry-hub-url>/api/v1/health` | Expected status: `{"status":"ok",...}`. |

If your GitHub token lacks org read permission, refresh scopes first:

```bash
gh auth refresh -h github.com -s read:org
```

Clone the repository and register the global plugin and standalone launchers (`~/.local/bin/agyis` and legacy alias `~/.local/bin/psl`):

```bash
git clone https://github.com/kuasha420/agyis-harness.git ~/Dev/agyis-harness
cd ~/Dev/agyis-harness
./agyis install --global
which agyis
```

*(If `agyis` is missing from `$PATH`, add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc` or `~/.zshrc`.)*

---

## 2. Hub Authentication, Privacy & Workspace Denylists

Authenticate once via your GitHub CLI session (or pass a PAT over stdin in headless environments):

```bash
agyis auth login --gh --endpoint <telemetry-hub-url>
agyis auth status
```

To target a local development or staging hub for a single repository without modifying global user config:

```bash
cd /path/to/<project-repo>
agyis auth login --endpoint http://127.0.0.1:8000 --workspace
```

*(Workspace config `<project>/.agyis/config.json` overrides `~/.config/agyis/config.json`.)*

### Client-Side Sanitization & Denylist Filtering

Before any session leaves your workstation, `harness/telemetry/redaction.py` strips tokens, credentials, and private home paths. To exclude confidential client or personal directories completely, add glob patterns to `~/.config/agyis/config.json`:

```json
{
  "endpoint": "<telemetry-hub-url>",
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

## 5. Multi-Device Knot Mesh Fleet Sync Verification

When syncing across physical workstations (`@desktop` anchor, `@laptop` compute worker, `@steamdeck` / handheld node), update each node and verify its telemetry & harness health remotely:

```bash
# Broadcast update + global install + sync across online mesh nodes
knot exec --all "cd ~/Dev/agyis-harness && git pull origin main && ./agyis install --global && agyis sync"

# Or check a specific strand via ControlMaster SSH (ADR-027)
agyis remote exec <target-node> "agyis status"
agyis remote triage <target-node>
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
| `AGYIS_SYNC_ENDPOINT` | `PSL_SYNC_ENDPOINT` | Telemetry hub endpoint URL (`<telemetry-hub-url>`) |
| `AGYIS_TELEMETRY_DB` | `PSL_TELEMETRY_DB` | Explicit SQLite database path (zero-CWD probing per ADR-030) |
| `AGYIS_DATA_DIR` | `PSL_DATA_DIR` | XDG data directory override (default `~/.local/share/agyis`) |
| `AGYIS_CONFIG_DIR` | `PSL_CONFIG_DIR` | XDG configuration directory (default `~/.config/agyis`) |
| `AGYIS_HARNESS_STATE_DIR` | `PSL_HARNESS_STATE_DIR` | Runtime hook state override (default `/tmp/agyis_harness_state_{uid}`) |
| `PSL_RETRY_BACKOFF` | — | Initial backoff seconds for transient 502/503/504 retries (`1.0`) |

---

## 7. Operator Troubleshooting & Verification Checklist

| Symptom | Cause | Resolution |
| :--- | :--- | :--- |
| `HTTP 401: Unauthorized` | GitHub PAT missing or expired | Run `agyis auth login --gh --endpoint <telemetry-hub-url>` |
| `HTTP 403: Forbidden` | Account lacks `<github-org>` org membership or `read:org` scope | Verify org membership via `gh api user/orgs --jq '.[].login'` and run `gh auth refresh -h github.com -s read:org` |
| `FileNotFoundError` / `0 sessions pushed` | Local SQLite DB has not been populated yet | Run `agyis audit extract` before `agyis sync` |
| `HTTP 413: Request Entity Too Large` | Legacy unchunked client | Pull latest `main` and re-run `./agyis install --global` |
| `database is locked` | Concurrent write outside WAL busy timeout | Wait briefly and retry; WAL mode is managed automatically |
| Local DB / Prisma `P1000` warning in `agyis doctor` | Port `5432` occupied by a foreign container | See [`repo-onboarding.md`](repo-onboarding.md#6-database-port-5432-collision-check-prisma-p1000) |

### Verification Checklist
- [ ] `agyis auth status` confirms active authentication against `<telemetry-hub-url>`.
- [ ] `agyis sync --dry-run` connects cleanly and previews pending counts without error.
- [ ] `agyis sync --service status` (or foreground `--watch`) confirms active synchronization.
- [ ] `agyis doctor` and `agyis status` pass cleanly on each synced workstation.
