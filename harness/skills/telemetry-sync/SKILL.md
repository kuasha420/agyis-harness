---
name: telemetry-sync
description: >-
  Standardized telemetry synchronization, cross-device delta replication, authenticated dry-run preview,
  background watch daemon management, and systemd service configuration for Agyis Harness.
  Use when synchronizing telemetry databases with the central hub, pulling cross-device agent trajectories,
  filtering by developer handle, configuring telemetry background daemons, or troubleshooting hub connectivity.
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# PSL Telemetry Sync: Hub Replication, Multi-Device Federation & Daemon Runbook

This skill establishes standardized operational runbooks for bi-directional telemetry synchronization, cross-device transcript replication, authenticated dry-run previews, background watch daemons, and systemd service integration with the central telemetry hub (`https://psl-harness.infra.purrfecthq.com`).

---

## 1. Canonical CLI Workflows

### 1.1 Standard Bi-Directional Synchronization
Extract active workspace transcripts into the local SQLite database and synchronize with the central hub:
```bash
# Ingest local raw transcripts into telemetry.db
agyis audit extract

# Synchronize local database with the central telemetry hub
agyis sync
```

### 1.2 Developer-Filtered Pull (Cross-Device Federation)
Pull trajectories authored by a specific developer handle across devices (e.g. laptop, desktop, handheld), bypassing default anti-echo reflection filters:
```bash
# Pull own transcripts authored on other devices
agyis sync --pull --developer kuasha420

# Authenticated preview of remote transcripts authored by user
agyis sync --pull --developer kuasha420 --dry-run
```

### 1.3 Fleet-Wide Corpus Ingestion
Pull telemetry across all developers and devices for fleet analytics or deep audit dissection:
```bash
# Pull fleet-wide transcripts across all developers
agyis sync --pull --all

# Pull delta corpus starting from specific ISO8601 watermark
agyis sync --pull --all --since 2026-01-01T00:00:00Z
```

### 1.4 Unidirectional & Dry-Run Preview Modes
Test network reachability, validate GitHub PAT credentials, and inspect pending push/pull counts without modifying local SQLite state or the remote hub:
```bash
# Push pending local sessions only
agyis sync --push

# Pull remote deltas only
agyis sync --pull

# Authenticated bi-directional preview against hub
agyis sync --dry-run

# Preview local pending push count
agyis sync --push --dry-run

# Preview pending fleet-wide pull count
agyis sync --pull --all --dry-run
```

### 1.5 Automated Background Watch Daemon & Systemd Unit
Configure continuous synchronization for unattended workstations and developer machines:
```bash
# Run continuous watch daemon in foreground (polls every 10s)
agyis sync --watch --interval 10.0

# Generate and install production systemd user service
mkdir -p ~/.config/systemd/user
agyis sync --systemd > ~/.config/systemd/user/agyis-sync.service
systemctl --user daemon-reload
systemctl --user enable --now agyis-sync.service

# Verify systemd service status
systemctl --user status agyis-sync.service
```

---

## 2. Architectural Invariants

### 2.1 Centralized Connection Factory & Concurrency (ADR-014, ADR-030)
- All SQLite telemetry connections use `harness.telemetry.db.get_db_connection(db_file)`.
- Enforces Write-Ahead Logging (`PRAGMA journal_mode = WAL`) and `PRAGMA busy_timeout = 30000` (30 seconds).
- Readers and writers never block each other. Concurrent CLI commands (`agyis status`, `agyis sync`) and background daemons run without database locks.

### 2.2 Network-Lock Decoupling Invariant
- Database connections are **never held open across remote HTTP network calls** (`urllib.request.urlopen`).
- Sessions are read from disk in bounded incremental batches prior to network transmission.
- Remote delta pages are fetched over HTTP, then ingested in localized sub-millisecond atomic transactions.

### 2.3 Delta Watermark Invariant (Cross-Device Purity)
- Watermark calculation for pulling remote sessions (`since`) strictly filters `WHERE origin_developer != 'local'`.
- Locally created and pushed sessions never advance or mask remote sync timestamps, ensuring transcripts from other devices are never skipped.

### 2.4 Transient Retry & Resilience Invariant
- Both push and pull engines implement fixed retry delay backoff (default 1.0s, configurable via `PSL_RETRY_BACKOFF` or parameter) for transient HTTP errors (502, 503, 504) and network dropouts (`URLError`) up to 3 attempts.
- Client authentication and authorization errors (HTTP 401, 403, 400) fail fast without retrying.

### 2.5 Clean-Room Hermetic Testing (ADR-015)
- Telemetry test suites (`tests/test_telemetry_sync.py`, `tests/test_cli.py`) execute hermetically without external network dependencies using `tempfile.TemporaryDirectory()`.
- Benchmark constraint: telemetry unit tests execute strictly under **1.0 second**.

---

## 3. Troubleshooting & Failure Recovery Runbook

### 3.1 HTTP 401: Unauthorized / Invalid Token
- **Symptom**: `✘ Telemetry sync authentication failed (HTTP 401: Unauthorized)`.
- **Diagnosis**: GitHub PAT token is expired, missing, or lacks required scopes.
- **Remediation**:
  ```bash
  # Check current auth status
  agyis auth status

  # Re-authenticate using GitHub CLI token
  agyis auth login --gh

  # Verify token against hub
  agyis sync --dry-run
  ```

### 3.2 HTTP 403: Forbidden / Organization Membership
- **Symptom**: `✘ Telemetry sync authorization failed (HTTP 403: Forbidden)`.
- **Diagnosis**: User is authenticated, but not an authorized member of the `purrfectsoft` GitHub organization.
- **Remediation**: Verify organization membership on GitHub or contact organization admin for access.

### 3.3 Connection / DNS Failure
- **Symptom**: `✘ Failed to connect to telemetry hub (https://psl-harness.infra.purrfecthq.com)`.
- **Diagnosis**: Workstation is offline or endpoint URL is misconfigured.
- **Remediation**:
  ```bash
  # Test hub health probe
  curl -sS https://psl-harness.infra.purrfecthq.com/api/v1/health

  # Check endpoint configuration
  echo $AGYIS_SYNC_ENDPOINT
  cat ~/.config/psl/config.json
  ```
