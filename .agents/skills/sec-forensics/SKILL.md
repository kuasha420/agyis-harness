---
name: sec-forensics
description: >-
  Standardized ephemeral read-only container triage, cloud credential revocation,
  remote triage execution, and security forensics report compilation runbook.
  Use when conducting containment and investigation on potentially compromised systems,
  isolating host environments with read-only Docker containers, revoking exposed cloud keys (GCP/AWS),
  executing non-invasive remote diagnostic scripts, or compiling forensics markdown reports to PDF.
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Purrfect Software Limited (PSL) -->

# PSL Security Forensics: Containment, Cloud Revocation & Triage Runbook

This skill establishes empirical, tool-native runbooks for emergency security containment, read-only isolated container triage, instant cloud credential revocation, remote memory-only script execution, and forensic audit report compilation.

---

## 1. Ephemeral Read-Only Container Triage (`docker run --rm -v /:/host:ro`)

### Invariant: Non-Invasive Read-Only Host Mount
When investigating a potentially compromised host or suspicious binaries, never execute unverified tools directly on the host or mount host root read-write (`:rw`). Always mount root as read-only (`/:/host:ro`) inside an ephemeral container (`--rm`) with network isolation (`--network none`) to prevent lateral movement, persistence alteration, or tampering with file timestamps (`atime`/`mtime`).

### Step 1.1: Launch Ephemeral Read-Only Analysis Shell
```bash
docker run --rm -it \
  --network none \
  -v /:/host:ro \
  alpine:latest sh
```

### Step 1.2: Forensic Integrity Inspection Inside Container
Inspect host cron jobs, systemd units, startup hooks, and suspicious executables:
```bash
# Check persistence crontabs and systemd services
ls -lchu /host/etc/cron* /host/etc/systemd/system/

# Compute SHA256 hash of suspicious binary
sha256sum /host/usr/local/bin/<suspicious_binary>

# Check recent modifications in system directories (within last 48 hours)
find /host/usr/bin /host/usr/sbin -type f -mtime -2 -exec ls -lh {} +

# Search for hidden files in temporary staging directories
ls -la /host/tmp /host/var/tmp /host/dev/shm
```

---

## 2. Emergency Cloud Credential Revocation

### Invariant: Instant Revocation Precedes Downstream Analysis
If cloud service account keys, API tokens, or secrets are leaked in logs, git history, or workspace files, revoke them immediately before reviewing access logs or investigating root cause.

### 2.1 Google Cloud Platform (GCP) IAM Key Revocation
List active keys for the affected service account:
```bash
gcloud iam service-accounts keys list --iam-account=<SERVICE_ACCOUNT_EMAIL>
```

Delete the compromised key immediately:
```bash
gcloud iam service-accounts keys delete <KEY_ID> \
  --iam-account=<SERVICE_ACCOUNT_EMAIL> \
  --quiet
```

If widespread compromise is suspected, disable the entire service account:
```bash
gcloud iam service-accounts disable <SERVICE_ACCOUNT_EMAIL>
```

### 2.2 AWS IAM Access Key Deactivation & Revocation
Deactivate the access key instantly:
```bash
aws iam update-access-key \
  --access-key-id <ACCESS_KEY_ID> \
  --status Inactive
```

Delete the deactivated key:
```bash
aws iam delete-access-key \
  --access-key-id <ACCESS_KEY_ID>
```

---

## 3. Remote Forensics via `harness.cli remote script`

### Invariant: Zero-Disk-Footprint Script Streaming
Never copy diagnostic scripts to remote target disks during live triage. Use `harness.cli remote script` to stream Python or shell scripts directly into remote interpreters over stdin.

### Step 3.1: Stream Non-Invasive Diagnostic Script
Stream local forensic triage script directly into the remote target without writing to remote storage:
```bash
python3 -m harness.cli remote script <target> ./triage_probe.py
```

### Step 3.2: Staged Execution with Automatic Trap Cleanup
When executing multi-command probes that require staging, use `--stage` to guarantee temporary file removal upon termination:
```bash
python3 -m harness.cli remote script <target> ./triage_probe.py --stage
```

### Step 3.3: Bounded Compact Health Triage
Run compact (<2KB) multi-component remote health triage:
```bash
python3 -m harness.cli remote triage <target>
```

---

## 4. Forensic Audit Report & Headless PDF Compilation

### Step 4.1: Structure Forensic Incident Report (`report.md`)
Draft findings following the standard security incident format:
- **Incident Summary**: Detection time, scope, affected systems.
- **Immediate Containment Actions**: Credentials revoked, network isolated.
- **Evidence Ledger**: SHA256 file hashes, timestamps, IP connection logs.
- **Root Cause & Remediation**: Ingress vector, permanent remediation steps.

### Step 4.2: Compile Markdown to PDF
Generate an official PDF forensic report using headless rendering tools:

#### Option A: Typst / Pandoc (Direct MD to PDF)
```bash
pandoc forensics_report.md -o forensics_report.pdf --pdf-engine=typst
```

#### Intermediate HTML Generation (for HTML/CSS-based engines)
```bash
pandoc forensics_report.md -s --toc -o forensics_report.html
```

#### Option B: Weasyprint (HTML/CSS to PDF)
```bash
python3 -m weasyprint forensics_report.html forensics_report.pdf
```

#### Option C: Headless Chromium PDF Export
```bash
chromium --headless --disable-gpu --run-all-compositor-stages-before-draw --print-to-pdf=forensics_report.pdf forensics_report.html
```
