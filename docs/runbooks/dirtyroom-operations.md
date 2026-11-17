<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Dirty-Room Operations Runbook: Preparation, Seeding, Priming & Maintenance

This operational runbook codifies standard operating procedures for provisioning, seeding, accelerating, and maintaining isolated reverse engineering workspaces ("dirty-rooms") under the Antigravity Immune System (Agyis) harness.

Governed by **PSL-INV-007** (Universal Cleanroom Reverse Engineering & Reconstruction Invariants) and **PSL-INV-009** (Pre-Analyzed Decompiler Cache & Direct Mount Invariant).

---

## 1. Prerequisites & Tooling

The Agyis Cleanroom RE toolchain requires a hermetic toolchain matrix across disassemblers, compilers, runtimes, and packet analyzers.

### 1.1 Required Tooling Matrix

| Tool | Minimum Version | Purpose | Discovery Path |
| :--- | :--- | :--- | :--- |
| **Java Development Kit (JDK)** | OpenJDK 21+ | Headless Ghidra runtime | `/usr/lib/jvm/java-21+`, `JAVA_HOME` |
| **Ghidra** | 11.0+ | Headless binary analyzer & decompiler | `/opt/ghidra/support/analyzeHeadless`, `GHIDRA_HOME` |
| **REA Tooling** | 6.5.0+ (6.9.0+ rec) | Stdio Model Context Protocol (MCP) RE bridge | `rea` CLI in `PATH`, `pnpm global` |
| **SQLite** | 3.35.0+ | Fast indexed symbol/packet storage | In-tree Python SQLite3 / system CLI |
| **GNU binutils (objdump)** | 2.38+ | Zero-timeout instruction disassembly | `/usr/bin/objdump` |
| **Wireshark / TShark** | 3.6.0+ | Network packet capture dissection & filtering | `/usr/bin/tshark` |

### 1.2 Automated Toolchain Diagnostic

Audit the host environment against the RE toolchain matrix:

```bash
# Inspect baseline and experimental RE provider chains
agyis doctor --experimental-rea

# Output indicates:
#   [PASS] ghidra       [core]    headless-ready -> /opt/ghidra/support/analyzeHeadless
#   [PASS] java         [core]    >=21           -> /usr/lib/jvm/java-27-openjdk
#   [PASS] objdump      [core]    2.47           -> /usr/bin/objdump
#   [PASS] rea_patch    [core]    active         -> GhidraLauncher.js
#   [PASS] dirtyroom_db [core]    schema-ready   -> .dirtyroom/symbols/dirtyroom.db
#   [PASS] tshark       [dynamic] N/A            -> /usr/bin/tshark
```

If any prerequisite is missing or outdated, run automated user-space healing:

```bash
agyis doctor --experimental-rea --heal
```

---

## 2. Zero-to-Hero Dirtyroom Preparation

A cleanroom reverse engineering project strictly bifurcates dirty artifacts (proprietary binaries, memory dumps, raw decompilation, network pcaps) from cleanroom source code.

```
Workspace Root (Repository)
├── .dirtyroom/                 <-- Quarantined by .gitignore (PSL-INV-007)
│   ├── ghidra/                 <-- Pre-analyzed Ghidra project (.gpr + .rep/)
│   ├── symbols/                <-- Indexed SQLite symbol database (dirtyroom.db)
│   ├── logs/                   <-- Daemon logs, headless analysis trace logs
│   ├── pcaps/                  <-- Captured network traces (.pcap, .pcapng)
│   ├── cache/                  <-- Query cache (.dirtyroom/cache/decompile/*.c)
│   └── dirtyroom.env           <-- Shell environment exports
├── dirtyroom                   <-- Symlink to .dirtyroom for Ghidra compatibility
├── docs/specs/                 <-- Cleanroom protocol & architectural specifications
└── crates/ or src/             <-- Cleanroom implementation (zero vendor bytes)
```

### 2.1 Step 1: Initialize Workspace Scaffolding

Scaffold the quarantined directory structure and initialize the SQLite schema:

```bash
agyis re init . --project ProjectX
```

This turnkey command idempotently establishes:
1. Directory hierarchy: `.dirtyroom/{ghidra,symbols,logs,pcaps,cache/decompile}`.
2. SQLite schema initialized at `.dirtyroom/symbols/dirtyroom.db` (`binaries`, `functions`, `strings`, `rtti_classes`, `packets`, `runs`).
3. Non-dot symlink alias: `dirtyroom -> .dirtyroom` (Ghidra headless analyzer strictly rejects directories beginning with a leading dot `.`).
4. Environment export script: `.dirtyroom/dirtyroom.env`.
5. Local and repository-level `.gitignore` quarantine rules.

### 2.2 Step 2: Source Environment Configuration

Source the generated environment variables in the active shell or automation scripts:

```bash
source .dirtyroom/dirtyroom.env
```

Contents of `.dirtyroom/dirtyroom.env`:
```bash
export AGYIS_DIRTYROOM="/path/to/workspace/.dirtyroom"
export REA_GHIDRA_PROJECT_DIR="/path/to/workspace/dirtyroom/ghidra"
export REA_GHIDRA_PROJECT_NAME="ProjectX"
export REA_DISASSEMBLER="ghidra"
export REA_GHIDRA_DIRECT_MOUNT="1"
```

### 2.3 Step 3: Apply REA Direct-Mount Acceleration Patch

Ghidra projects for large binaries ($>10\text{MB}$, often multi-hundred megabytes) take upwards of 1.5GB on disk. Standard REA spawns temporary analysis directories on every query, cloning the entire `.rep/` folder and stalling turns for 8–15 seconds.

Apply the zero-copy direct mount patch (PSL-INV-009):

```bash
# Check patch status
agyis re patch-rea --check

# Apply zero-copy direct mount patch
agyis re patch-rea --apply
```

This patches `GhidraLauncher.js` in `rea-agents` to enforce `-noanalysis` and `-readOnly` flags against the existing pre-analyzed Ghidra project directly in `.dirtyroom/ghidra/`, eliminating temporary disk clones and unfreezing the decompiler pipeline.

---

## 3. Seeding & Ingestion

Once the dirtyroom is initialized, seed it with target binaries and observed network captures.

### 3.1 Step 1: Register and Pre-Analyze Target Binaries

Place target binaries (PE, ELF, Mach-O) in `.dirtyroom/binaries/` or point directly to their location:

```bash
# Run headless Ghidra pre-analysis
agyis re pre-analyze /path/to/target.exe --project ProjectX
```

During pre-analysis:
1. Headless Ghidra executes once in background with full analysis passes (decompilation analysis, RTTI class recovery, export/import parsing).
2. The Ghidra project repository (`ProjectX.gpr` and `ProjectX.rep/`) is committed to `.dirtyroom/ghidra/`.
3. Extracted metadata is automatically ingested into `.dirtyroom/symbols/dirtyroom.db`:
   - `binaries`: SHA-256 digest, file size, architecture, format.
   - `functions`: Names, addresses, sizes, signatures, export flags.
   - `strings`: Static ASCII and Unicode strings with virtual addresses.
   - `rtti_classes`: Class names, demangled names, vtable addresses, base inheritance chains.

### 3.2 Step 2: Seed Network Packet Captures (PCAPs)

Ingest live network session captures into the SQLite `packets` table and link them to binary runs:

```bash
# Seed default or specific PCAP
agyis re seed --pcap .dirtyroom/pcaps/retail_session.pcap --binary target.exe --limit 5000

# JSON output mode for automation
agyis re seed --pcap .dirtyroom/pcaps/retail_session.pcap --json
```

The seed engine:
- Supports zero-dependency pure Python libpcap extraction (handling both microsecond and nanosecond captures).
- Automatically falls back to `tshark` for complex encapsulations or `.pcapng` containers.
- Records frame metadata: frame number, timestamp epoch, protocol (TCP/UDP/ICMP), src/dst IP addresses and ports, payload length, and frame summary.
- Links ingested frames to the binary row in `binaries` and creates an execution record in `runs`.

### 3.3 Step 3: Fast Sub-Millisecond Symbol Querying

With metadata seeded into SQLite, query functions, strings, and RTTI classes in $<2\text{ms}$ without invoking heavyweight disassemblers:

```bash
# Search across all symbols, strings, and RTTI classes
agyis re find "Connection"

# Target specific category
agyis re find "Login" --type func --limit 20
agyis re find "http://" --type str --limit 10
agyis re find "GameEngine" --type rtti
```

---

## 4. Priming & Acceleration

To satisfy **PSL-INV-009 §2** (sub-2-second benchmark invariant), the RE pipeline leverages a persistent supervisor daemon and deterministic query cache.

```
Query: agyis re decompile <function>
                │
                ▼
      ┌───────────────────┐
      │  Cache Hit?       │ ── Yes (<5ms) ──> Output from .dirtyroom/cache/
      └───────────────────┘
                │ No
                ▼
      ┌───────────────────┐
      │ REA Bridge Daemon │ ── Yes (<0.8s) ─> Sub-second in-memory Ghidra query
      └───────────────────┘
                │ Fallback
                ▼
      ┌───────────────────┐
      │ Direct REA CLI    │ ── Subprocess ──> Direct mount (-noanalysis -readOnly)
      └───────────────────┘
```

### 4.1 Step 1: Launch Persistent REA MCP Bridge Daemon

Cold JVM launches incur an 8–10s startup penalty. Launch the background REA bridge supervisor daemon to maintain warm Ghidra instances and open stdio MCP connections:

```bash
# Start background supervisor daemon
agyis re daemon start

# Inspect daemon health, uptime, and mounted projects
agyis re daemon status

# JSON status for health check scripts
agyis re daemon status --json
```

### 4.2 Step 2: Pre-Warm Decompiler Query Cache (`agyis re prime`)

Pre-warm the decompiler query cache on priority functions (e.g. exported entrypoints, network dispatchers, major subsystem loops):

```bash
# Pre-warm top 25 priority functions from SQLite
agyis re prime --top 25 --binary target.exe

# Pre-warm functions from an explicit symbols list
agyis re prime --file critical_symbols.txt --timeout 45.0

# Preview candidates without decompiling
agyis re prime --top 50 --dry-run
```

The priming engine:
1. Sorts functions by export status and size.
2. Checks `.dirtyroom/cache/decompile/{cache_key}.c`.
3. Issues sequential decompilation calls through the warm REA bridge.
4. Writes resulting C pseudo-code to `.dirtyroom/cache/decompile/` while preserving authentic client hit/miss telemetry in `stats.json`.

### 4.3 Step 3: Benchmark Verification

Validate that decompilation queries complete within required benchmark bounds:

```bash
# Cached query verification (<5ms)
time agyis re decompile UTgMatchLobby_QueueState

# Forced cache-refresh verification (<0.8s via warm daemon)
time agyis re decompile UTgMatchLobby_QueueState --no-cache
```

---

## 5. Routine Maintenance & Hygiene

Long-running reverse engineering sessions accumulate stale lock files, trace logs, and database page fragmentation.

### 5.1 Step 1: Inspect System Status

```bash
# Overall dirtyroom and REA health
agyis re status

# Decompiler query cache usage and hit rates
agyis re cache status
```

### 5.2 Step 2: Clear Query Cache

When target binaries are re-analyzed or updated, purge stale decompiler cache entries:

```bash
# Preview files to be purged
agyis re cache clear --dry-run

# Purge all decompiler cache entries
agyis re cache clear --type decompile
```

### 5.3 Step 3: Turnkey Hygiene & Cleanup (`agyis re clean`)

Orphan Ghidra lock files (`*.lock`, `*.lock~`) prevent subsequent read-only mounts. Clean stale locks, prune old logs, and vacuum the SQLite database:

```bash
# Preview all pending maintenance actions
agyis re clean --dry-run

# Execute full maintenance pass (locks, logs, database vacuum)
agyis re clean

# Granular maintenance
agyis re clean --locks    # Safely purge orphan Ghidra .lock files
agyis re clean --logs     # Prune old logs (preserves active daemon logs)
agyis re clean --vacuum   # Run SQLite VACUUM, REINDEX, and ANALYZE
```

The hygiene engine checks `/proc` before removing Ghidra locks, ensuring active `analyzeHeadless` processes are not interrupted.

### 5.4 Step 4: Daemon Lifecycle Governance

When switching projects or rebooting the workstation, stop the supervisor daemon cleanly:

```bash
# Graceful stop via SIGTERM with SIGKILL fallback
agyis re daemon stop
```

---

## 6. Cleanroom Quarantine Invariants (PSL-INV-007)

The ultimate deliverable of reverse engineering is cleanroom specifications and implementations. The dirtyroom is strictly quarantined.

### 6.1 The Air-Gap Membrane
- **Never commit `.dirtyroom/`**: Must remain quarantined in `.gitignore`.
- **Never copy vendor disassembly into git**: No raw assembly listings, vendor C++ decompilations, or binary blobs in repository commits.
- **Pure Specification Flow**: Only markdown specifications (`docs/specs/*.md`), JSON field schemas, and typed obligation ledgers may transition across the cleanroom membrane.

### 6.2 Obligation Ledgers
Every claim about an unmapped protocol, opcode, or struct layout must link to an immutable evidence record:

```json
{
  "obligation_id": "OBL-AUTH-001",
  "subject": "Handshake Sequence",
  "claim": "Client sends CMarshal Hello (0x01) followed by Login Response (0x02)",
  "evidence_type": "PCAP_FRAME",
  "evidence_id": "frame_104",
  "pcap_file": "retail_session.pcap",
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "verification_gate": "cargo test test_golden_stream"
}
```

Verify compliance before completing tasks:

```bash
# Verify cleanroom specifications contain zero code leaks
agyis verify --spec

# Formally verify typed cleanroom obligations against evidence
agyis verify
```

---

## 7. Operational Troubleshooting Matrix

| Symptom | Root Cause | Remediation |
| :--- | :--- | :--- |
| `Ghidra project contains leading dot` | Ghidra rejects `.dirtyroom` path components | Use symlink `dirtyroom -> .dirtyroom` created by `agyis re init` (DEF-BB-038). |
| `Ghidra project locked / Read-only error` | Stale orphan `*.lock` from crashed process | Run `agyis re clean --locks` to clear stale locks safely. |
| `PSL-INV-009 §1 Violation: Target binary exceeds 10MB` | Binary $>10\text{MB}$ invoked without pre-analysis | Run `agyis re pre-analyze <binary>` before decompiling. |
| `Decompilation SLA timeout (>180s)` | Direct mount patch not applied; REA cloning `.rep/` | Run `agyis re patch-rea --apply` to enable direct mount. |
| `Cold JVM startup latency (8-10s per query)` | REA MCP bridge supervisor daemon not running | Run `agyis re daemon start` to warm up JVM and language providers. |
| `Dirtyroom database missing or locked` | SQLite database locked or fragmented | Run `agyis re clean --vacuum` to reindex and optimize pages. |
| `PCAP ingestion fails on .pcapng` | Pure-Python parser requires libpcap format | Ensure `tshark` is installed (`sudo pacman -S wireshark-cli`). |
