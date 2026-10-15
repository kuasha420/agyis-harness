---
title: Agyis Harness Telemetry Sync Runbook
description: Comprehensive operational runbook for bi-directional telemetry synchronization, cross-device federation, authenticated dry-runs, background watch daemons, and systemd integration.
version: 1.0.0
last_updated: 2026-10-15
target_audience: [developer, operator, devops]
related_adrs: [ADR-014, ADR-015, ADR-030]
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# 🔄 Agyis Harness: Telemetry Synchronization & Fleet Federation Runbook

This runbook documents the architecture, operational CLI workflows, background automation, and troubleshooting procedures for the Agyis Harness telemetry synchronization subsystem (`agyis sync`).

---

## 1. Subsystem Architecture

The Telemetry Sync subsystem enables bi-directional replication of agent trajectory sessions, steps, tool calls, and operator steering interventions between local developer workstations (`data/telemetry.db`) and the central telemetry hub gateway (`https://psl-harness.infra.purrfecthq.com`).

```
Local Client (CLI / Background Daemon)           Central Telemetry Hub Gateway
┌──────────────────────────────────────┐       ┌─────────────────────────────────┐
│ agyis sync [options]                 │       │ https://psl-harness.infra...    │
│   ├── cmd_sync()                     │ HTTPS │                                 │
│   └── sync_telemetry()               │ REST  │ ┌─────────────────────────────┐ │
│         ├── push_local_sessions()    ├──────►│ │ POST /api/v1/sync/push      │ │
│         │     (sanitized batch push) │       │ │ (idempotent upsert & dedup) │ │
│         ├── pull_remote_sessions()   │◄──────┤ │ GET  /api/v1/sync/pull      │ │
│         │     (delta extract & merge)│       │ │ (anti-echo filtered delta)  │ │
│         └── harness/telemetry/db.py  │       │ └─────────────────────────────┘ │
│               (WAL + busy_timeout)   │       │ PostgreSQL / SQLite storage     │
└──────────────────────────────────────┘       └─────────────────────────────────┘
```

---

## 2. Canonical CLI Command Reference

### 2.1 Standard Bi-Directional Sync
Synchronizes local transcripts with the central hub: pushes pending local sessions first, then pulls new remote deltas:
```bash
# Ingest active transcripts from ~/.gemini/antigravity/ into local database
agyis audit extract

# Run bi-directional sync against central hub
agyis sync
```

### 2.2 Developer-Filtered Pull (Cross-Device Trajectory Synchronization)
Allows developers working across multiple physical devices (Desktop, Laptop, Steam Deck) to pull their own transcripts onto the current workstation without being blocked by server-side anti-echo filters:
```bash
# Pull all transcripts authored by kuasha420 across all devices
agyis sync --pull --developer kuasha420

# Authenticated preview of pending pull count
agyis sync --pull --developer kuasha420 --dry-run
```

### 2.3 Fleet-Wide Corpus Ingestion
Retrieves the complete remote telemetry corpus across all developers and devices for deep empirical analysis:
```bash
# Pull fleet-wide transcripts (all developers)
agyis sync --pull --all

# Pull delta corpus modified or created on/after ISO timestamp
agyis sync --pull --all --since 2026-01-01T00:00:00Z
```

### 2.4 Unidirectional & Dry-Run Modes
Preview pending operations or push/pull independently:
```bash
# Push only local sessions
agyis sync --push

# Pull only remote deltas
agyis sync --pull

# Authenticated bi-directional dry-run preview (verifies network and credentials)
agyis sync --dry-run

# Preview pending local push count
agyis sync --push --dry-run

# Preview pending fleet-wide pull count
agyis sync --pull --all --dry-run
```

### 2.5 Automated Background Daemon & Systemd Unit
Keep local telemetry synchronized automatically in the background:
```bash
# Foreground watch daemon (polls every 10 seconds)
agyis sync --watch --interval 10.0

# Generate systemd user service definition
agyis sync --systemd > ~/.config/systemd/user/agyis-sync.service

# Enable and start the user service
systemctl --user daemon-reload
systemctl --user enable --now agyis-sync.service

# Inspect daemon logs
journalctl --user -u agyis-sync.service -f
```

---

## 3. Concurrency & Database Invariants

### 3.1 Centralized Connection Factory (`harness/telemetry/db.py`)
All SQLite database connections use the centralized factory `get_db_connection(db_file)`:
- **Write-Ahead Logging**: `PRAGMA journal_mode = WAL;`
- **Busy Timeout**: `PRAGMA busy_timeout = 30000;` (30 seconds)
- **Normal Disk Sync**: `PRAGMA synchronous = NORMAL;`
- **Foreign Keys**: `PRAGMA foreign_keys = ON;`

### 3.2 Network-Lock Decoupling
SQLite database connections are **never held open across remote HTTP network calls**:
1. **Push Flow**: Local candidate sessions, steps, and tools are read into in-memory data structures, and the database connection is closed. HTTP POST transmission proceeds over the network. Only after HTTP 200 is received does a short-lived connection open to update `remote_synced_at`.
2. **Pull Flow**: Delta pages are requested over HTTP without holding an active database connection. When a page arrives, a short-lived connection ingests rows in an atomic transaction and closes immediately.

### 3.3 Watermark Isolation for Cross-Device Pulls
When computing the delta pull watermark (`since`), queries filter out local sessions:
```sql
SELECT MAX(remote_synced_at) FROM sessions
WHERE origin_developer != 'local' AND origin_developer IS NOT NULL;
```
This guarantees that pushing local sessions on this workstation never advances or corrupts the watermark, ensuring historical transcripts authored on other machines are cleanly pulled.

### 3.4 Transient Error Resilience
Both push and pull operations implement transient retries:
- **Eligible Status Codes**: HTTP 502 (Bad Gateway), HTTP 503 (Service Unavailable), HTTP 504 (Gateway Timeout), and network `URLError`.
- **Backoff**: Fixed retry delay (default 1.0s, configurable via `PSL_RETRY_BACKOFF` or parameter) across up to 3 attempts.
- **Fast Failure**: Client errors (HTTP 400, 401, 403, 422) fail fast without retrying.

---

## 4. Troubleshooting & Operational Diagnostics

| Issue | Verbatim Error Message | Diagnosis | Remediation |
|---|---|---|---|
| **Invalid Token** | `✘ Telemetry sync authentication failed (HTTP 401: Unauthorized).` | GitHub PAT expired or revoked. | Run `agyis auth login --gh` to refresh token from GitHub CLI. |
| **Forbidden** | `✘ Telemetry sync authorization failed (HTTP 403: Forbidden).` | User is not an authorized member of `purrfectsoft`. | Confirm organization membership at `https://github.com/orgs/purrfectsoft`. |
| **Unreachable Hub** | `✘ Failed to connect to telemetry hub` | Workstation offline or DNS resolution error. | Check internet connectivity or verify `AGYIS_SYNC_ENDPOINT`. |
| **Database Busy** | `✘ SQLite database error: database is locked` | Another process held exclusive write transaction. | Wait for background tasks to finish; ensure WAL mode is active. |

---

## 5. Verification Checklist

1. [ ] `python3 -m harness.cli test` passes with 100% success.
2. [ ] Total test execution time is `<1.0s` for hermetic sync test suite.
3. [ ] `agyis sync --dry-run` connects to the hub and previews pending counts.
4. [ ] `agyis sync --pull --developer <user> --dry-run` queries remote counts without mutating local DB.
5. [ ] `agyis sync --systemd` prints valid systemd service definition.
