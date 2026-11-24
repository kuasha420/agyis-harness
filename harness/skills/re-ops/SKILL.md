---
name: re-ops
description: >-
  Standardized cleanroom reverse engineering, dirty-room operations, pre-analyzed Ghidra
  direct-mount acceleration, and 4-vector protocol/binary verification runbook (PSL-RE-001).
  Use when scaffolding quarantined .dirtyroom workspaces, executing agyis re
  lifecycle commands, managing REA MCP bridge daemons and query caches, auditing binary
  branch gates, or validating typed cleanroom specifications and obligation ledgers.
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Agyis Reverse Engineering Operations: Cleanroom & Dirty-Room Runbook (`PSL-RE-001`)

This skill houses the complete **`PSL-RE-001` On-Demand Domain Pack** (Cleanroom Reverse Engineering & Pre-Analyzed Ghidra Cache). It establishes empirical, target-agnostic standard operating procedures for quarantined dirty-room management, pre-analyzed Ghidra direct-mount acceleration, `rea@6.9.0` obligation ledgers, and evidence-backed binary and protocol reconstruction.

## Table of Contents
1. [Cleanroom Separation and Quarantine Membrane](#1-cleanroom-separation-and-quarantine-membrane)
2. [Pre-Analyzed Ghidra Direct-Mount and Sub-2s Benchmark SLA](#2-pre-analyzed-ghidra-direct-mount-and-sub-2s-benchmark-sla)
3. [Complete agyis re Lifecycle Palette](#3-complete-agyis-re-lifecycle-palette)
4. [Universal 4-Vector Cleanroom Verification Methodology](#4-universal-4-vector-cleanroom-verification-methodology)
5. [The 5-Step REA Surgical Escalation Ladder](#5-the-5-step-rea-surgical-escalation-ladder)
6. [Cleanroom Verification Gates and Obligation Ledgers](#6-cleanroom-verification-gates-and-obligation-ledgers)
7. [References and Layer Extensibility](#7-references-and-layer-extensibility)

---

## 1. Cleanroom Separation and Quarantine Membrane

Every reverse engineering workspace MUST enforce a strict air-gap membrane (**PSL-RE-001 §1**) separating proprietary analysis artifacts (**dirty room**) from distributable specifications and implementations (**clean room**).

```
+--------------------------------------------------------------------------------+
|                       DIRTY ROOM (Quarantined / .gitignore)                    |
|                                                                                |
|  [Target Binaries]     [Captured Network Traces]     [Pre-Analyzed Projects]   |
|         |                          |                            |              |
|         v                          v                            v              |
|  REA / Ghidra / objdump       tshark / libpcap        .dirtyroom/symbols/*.db  |
|  (Branch & Xref Audits)      (Stream Carving)          (Sub-ms Symbol Index)   |
+--------------------------------------------------------------------------------+
                                     |
                                     | Cleanroom Extraction Boundary
                                     | (Specs, JSON Schemas, Obligation Ledgers)
                                     v
+--------------------------------------------------------------------------------+
|                       CLEAN ROOM (Version-Controlled Repo)                     |
|                                                                                |
|  Vector 1: Static Schema Conformance Tests (sub-second codec & layout checks)  |
|  Vector 2: Offline Golden Replay Fixtures  (bit-level hermetic stream parity)  |
|  Vector 3: Milestone State Machine & Branch-Gate Audits                        |
|  Vector 4: Automated End-to-End Verification & Obligation Ledger Gates         |
+--------------------------------------------------------------------------------+
```

### Core Quarantine Invariants (PSL-RE-001 §1)
1. **Zero Proprietary Code or Bytes in Git**: Never commit target binaries, raw disassembly listings, decompiled C/C++ pseudo-code, vendor symbol tables, `.gpr`/`.rep` databases, or `.dirtyroom/` caches into version control.
2. **Quarantined Workspace Layout**: Keep all dirty-room analysis state inside `.dirtyroom/` (excluded via `.gitignore`), resolving a non-dot Ghidra project path when launching headless Ghidra so leading-dot paths never cause rejection.
3. **Pure Specification Transfer**: Only human/agent-authored specifications (`docs/specs/**`), declarative field schemas, hermetic fixtures, and typed obligation ledgers (`.agents/ledger/**`) may cross into version control.
4. **No Speculative Assumptions (`PSL-INV-002`)**: Unobserved protocol paths, ambiguous structures, or incomplete findings must be tracked explicitly as residual unknowns until resolved by cited SHA-256 evidence.

---

## 2. Pre-Analyzed Ghidra Direct-Mount and Sub-2s Benchmark SLA

### Invariant: Mandatory Pre-Analysis for Binaries > 10 MB (PSL-RE-001 §2)
Never invoke ad-hoc headless decompilers or MCP analysis tools on target binaries exceeding **10 MB** without a pre-analyzed Ghidra project repository (`.gpr` + `.rep/`) mounted with `-noanalysis` and `-readOnly`.

### 2.1 Pre-Flight Toolchain Audit
Verify JDK 21+, Ghidra 11.0+, REA CLI/MCP (`rea@6.9.0`), SQLite, `objdump`, and `tshark` before starting analysis:
```bash
# Deep opt-in RE toolchain audit (keeps standard 'agyis doctor' < 1.0s)
agyis doctor --experimental-rea

# Safe zero-sudo user-space healing and upstream REA skill provisioning
agyis doctor --experimental-rea --heal
```

### 2.2 Three-Tier Acceleration Hierarchy
To meet the **PSL-RE-001 §2** sub-2-second benchmark SLA and eliminate 8–10s cold JVM starts and multi-GB `.rep/` disk clones, select the right query path across the three acceleration tiers:

```
+-----------------------------------------------------------------------------+
| CLI Path: agyis re decompile <procedure>                                    |
|   -> Tier 1: Disk Cache (.dirtyroom/cache/decompile/*.c) -- Hit (<5ms)      |
|   -> Miss / --no-cache -> Tier 3: Direct-Mount CLI (-noanalysis -readOnly)  |
+-----------------------------------------------------------------------------+
| Interactive MCP Path: REA MCP tools (procedure_pseudo_code / assembly)      |
|   -> Tier 2: Persistent REA MCP Bridge (`agyis re daemon start`) (<0.8s)    |
+-----------------------------------------------------------------------------+
```

| Tier | Mechanism | Query Path / Command | Latency Target |
| :--- | :--- | :--- | :--- |
| **Tier 1 (Cache)** | Deterministic disk cache | `agyis re decompile` hit (pre-warm via `agyis re prime`, inspect via `agyis re cache status`) | `<5 ms` |
| **Tier 2 (Daemon)** | Persistent REA MCP bridge | Warm `rea mcp` managed by `agyis re daemon start` (used by REA MCP tool calls) | `<0.8 s` |
| **Tier 3 (Direct Mount)** | Zero-copy in-place Ghidra mount | `agyis re decompile` cache miss / `--no-cache` with `agyis re patch-rea --apply` (`REA_GHIDRA_DIRECT_MOUNT=1`) | `<10 s` (cold CLI) |

> **Fail-Fast SLA Rule**: Any decompiler query exceeding **10.0 seconds** indicates cache bypass, an unpatched REA launcher cloning `.rep/`, or missing pre-analysis. Abort and remediate via `agyis re patch-rea --check`, `agyis re status`, and `agyis re daemon status` instead of stalling agent turns. Note that `agyis re decompile --no-cache` intentionally bypasses Tier 1 and runs Tier 3 direct-mount CLI; use REA MCP tools with a warm daemon for `<0.8 s` uncached interactive queries.

---

## 3. Complete agyis re Lifecycle Palette

The `agyis re` CLI provides a turnkey 15-subcommand lifecycle covering scaffolding, pre-analysis, seeding, acceleration, querying, and maintenance.

### 3.1 Provisioning, Patching & Pre-Analysis
```bash
# 1. Scaffold quarantined .dirtyroom/{ghidra,symbols,logs,pcaps,cache/decompile}, SQLite DB,
#    quarantine .gitignore rules, and .dirtyroom/dirtyroom.env
agyis re init . --project TargetAnalysis

# 2. Export direct-mount environment variables into active shell
source .dirtyroom/dirtyroom.env

# 3. Verify and apply REA zero-copy direct-mount patch (-noanalysis -readOnly)
agyis re patch-rea --check
agyis re patch-rea --apply
# Revert upstream patch if needed:
agyis re patch-rea --revert

# 4. Run one-time headless Ghidra pre-analysis and index symbols into SQLite
agyis re pre-analyze /path/to/target.bin --project TargetAnalysis
# Re-index an updated binary:
agyis re pre-analyze /path/to/target.bin --project TargetAnalysis --overwrite
```

### 3.2 Seeding, Daemon Warm-Up & Cache Priming
```bash
# 5. Ingest libpcap / pcapng traces into SQLite 'packets' table linked to binary runs
agyis re seed --pcap .dirtyroom/pcaps/session.pcap --binary target.bin --limit 5000

# 6. Start and inspect the persistent REA MCP bridge supervisor daemon
agyis re daemon start
agyis re daemon status --json

# 7. Pre-warm the deterministic decompiler cache on priority symbols (<5ms hits)
agyis re prime --top 25 --binary target.bin --dry-run
agyis re prime --top 25 --binary target.bin
agyis re prime --file priority_symbols.txt --timeout 45.0
```

### 3.3 Sub-Millisecond Querying & Binary Inspection
```bash
# 8. Inspect overall dirty-room, Ghidra project, SQLite metrics, and patch health
agyis re status
agyis re status --json

# 9. Sub-millisecond SQLite lookup across functions, strings, and RTTI classes
agyis re find "AuthSession" --type all --limit 25
agyis re find "Dispatch" --type func --limit 20
agyis re find "protocol://" --type str --limit 10
agyis re find "NetworkHandler" --type rtti

# 10. Accelerated decompilation (<5ms Tier 1 cache hit; Tier 3 direct-mount CLI on miss/--no-cache;
#     use REA MCP tools with a warm daemon for <0.8s uncached interactive queries).
#     Auto-resolves interior virtual addresses (e.g. 0x140bc8795 -> FUN_140bc8790 +0x5) to entrypoint.
agyis re decompile AuthSession_VerifyToken --binary target.bin
agyis re decompile 0x140001a50 --binary target.bin
agyis re decompile AuthSession_VerifyToken --binary target.bin --no-cache --timeout 60.0

# 11. Zero-timeout native disassembly via objdump (accepts hex address or function name)
agyis re disasm 0x140001a20 --binary target.bin --bytes 128 --limit 50
agyis re disasm AuthSession_VerifyToken --binary target.bin

# 12. Dual-mode cross-reference scan (Mode A: SQLite pre-analyzed cache; Mode B: binary direct scan)
#     Scans relative CALL/JMP opcodes in code and 4/8-byte pointers in data across PE32/PE32+
agyis re xrefs 0x140001a20 --binary target.bin
agyis re xrefs 0x140001a20 --binary target.bin --type code
agyis re xrefs 0x140001a20 --binary target.bin --type data --json

# 13. Address inspection, translation (VA <-> RVA <-> File Offset) & symbol attribution
agyis re addr 0x140001a50 --binary target.bin
agyis re addr 0x1a50 --binary target.bin
agyis re addr 0x140001a50 --binary target.bin --json

# 14. Bounded packet capture inspection via tshark
agyis re pcap .dirtyroom/pcaps/session.pcap --limit 50 --filter "tcp.port == 8443"
```

### 3.4 Cache Governance, Hygiene & Teardown
```bash
# 15a. Inspect or clear deterministic query cache
agyis re cache status
agyis re cache clear --type decompile --dry-run
agyis re cache clear --type all

# 15b. Turnkey hygiene: purge orphan Ghidra .lock files (with /proc safety checks),
#      prune rotated logs (preserving active daemon logs), and VACUUM/REINDEX SQLite
agyis re clean --dry-run
agyis re clean --locks --logs --vacuum
agyis re clean

# 15c. Gracefully stop background REA MCP bridge daemon when switching projects
agyis re daemon stop
```

### 3.5 Subcommand Quick-Reference Matrix

| Subcommand | Purpose | Key Flags |
| :--- | :--- | :--- |
| `agyis re init` | Scaffold `.dirtyroom/`, SQLite schema, quarantine `.gitignore` & env | `[path]`, `--project`, `--json` |
| `agyis re status` | Report dirty-room, Ghidra `.gpr`/`.rep`, DB metrics & patch state | `--json` |
| `agyis re patch-rea` | Check, apply, or revert REA zero-copy direct-mount patch | `--check`, `--apply`, `--revert`, `--json` |
| `agyis re pre-analyze` | Run one-time headless Ghidra analysis & SQLite indexing (alias: `preanalyze`) | `<binary>`, `--project`, `--overwrite`, `--json` |
| `agyis re seed` | Ingest `.pcap`/`.pcapng` frames into SQLite `packets` & `runs` | `--pcap`, `--binary`, `--limit`, `--json` |
| `agyis re daemon` | Manage persistent REA MCP bridge supervisor daemon | `status\|start\|stop`, `--foreground`, `--json` |
| `agyis re prime` | Pre-warm decompiler cache on top or listed symbols | `--top`, `--file`, `--binary`, `--timeout`, `--dry-run`, `--json` |
| `agyis re find` | Sub-millisecond SQLite search over functions, strings & RTTI | `<pattern>`, `--type all\|func\|str\|rtti`, `--limit`, `--json` |
| `agyis re decompile` | Cached / direct-mount CLI decompilation with smart interior procedure resolution | `<procedure>`, `--binary`, `--timeout`, `--no-cache` |
| `agyis re disasm` | Native `objdump` Intel-syntax disassembly by address or symbol | `<target>`, `--binary`, `--bytes`, `--limit` |
| `agyis re xrefs` | Dual-mode cross-reference scan (pre-analyzed SQLite + direct binary scan) | `<hex_addr>`, `--type all\|code\|data`, `--binary`, `--json` |
| `agyis re addr` | Address inspection & translation (VA <-> RVA <-> File Offset) with symbol lookup | `<address>`, `--binary`, `--json` |
| `agyis re pcap` | Bounded `tshark` packet summary with optional display filter | `<file>`, `--limit`, `--filter` |
| `agyis re cache` | Inspect hit rates/size or purge decompiler cache entries | `status\|clear`, `--type all\|decompile`, `--dry-run`, `--json` |
| `agyis re clean` | Remove stale Ghidra locks, prune old logs, vacuum SQLite DB | `--locks`, `--logs`, `--vacuum`, `--force`, `--dry-run`, `--json` |

---

## 4. Universal 4-Vector Cleanroom Verification Methodology

Avoid ad-hoc guesswork or brittle manual debugging against live binaries. Ground every cleanroom reconstruction across four ordered verification vectors:

### Vector 1: Static Schema Conformance
*Verify field IDs, scalar widths, endianness, alignment, and type tags hermetically in milliseconds.*
- Extract declarative field/opcode schemas into cleanroom JSON test fixtures (e.g., `tests/fixtures/protocol_schema.json`).
- Query field definitions deterministically without flooding context:
  ```bash
  grep -n -C 4 '"id": <FIELD_ID>' tests/fixtures/protocol_schema.json || [ $? -eq 1 ]
  ```
- Assert that every constant, struct layout, and serializer in the cleanroom codebase conforms to the declarative schema before executing any live target binary.

### Vector 2: Offline Golden Replay Fixtures
*Prove bit-level parser, framing, and compression parity against authentic captured streams offline.*
- Carve clean, bounded protocol payloads from quarantined captures into hermetic test fixtures:
  ```bash
  tshark -r .dirtyroom/pcaps/session.pcap \
    -Y "tcp.port == <PORT>" -T fields -e tcp.payload \
    | tr -d '\n' | xxd -r -p > tests/fixtures/golden_stream.bin
  ```
- Replay golden frames in memory via project-native unit tests to guarantee zero framing drift across refactors.

### Vector 3: Branch-Gate State Machine Audits
*Decompose reconstruction into discrete state milestones and verify every gating predicate.*
- Define ordered behavioral milestones (e.g., Transport Handshake -> Authentication -> Session Negotiation -> Active State Replication).
- Whenever a target fails to advance across a milestone boundary, locate the exact gating condition in the binary:
  1. Locate candidate handlers via `agyis re find "<StateSymbol>" --type func`.
  2. Inspect conditional predicates (`cmp`, `test`, `je`/`jne`, struct offsets) via `agyis re decompile`, `agyis re disasm`, and `agyis re xrefs` (or REA MCP tools `procedure_assembly` / `procedure_pseudo_code`).
  3. Update the cleanroom specification and state machine so the exact precondition is satisfied before issuing downstream messages.

### Vector 4: Automated End-to-End Verification
*Validate full behavioral parity with repeatable, non-interactive harnesses after Vectors 1–3 pass.*
- Run the repository's native automated test suite and non-interactive integration or end-to-end harness with bounded timeouts, structured log capture, and explicit milestone assertions.
- Never rely on manual playtesting or visual babysitting when an automated watchdog check can assert exit code 0 deterministically.

---

## 5. The 5-Step REA Surgical Escalation Ladder

When an automated verification run hangs, disconnects unexpectedly, or fails to cross a state gate, follow this deterministic 5-step ladder instead of guessing wire formats:

```
[Automated Verification Hangs or Fails at Gate]
                      |
                      v
[Step 1: Inspect Execution & Watchdog Logs]
   -> Isolate the last completed transition, error code, or silent stream drop
                      |
                      v
[Step 2: Target & Symbol Routing]
   -> agyis re find "<pattern>" (SQLite <2ms) or REA open_binary on target module
                      |
                      v
[Step 3: Branch-Gate & Xref Audit]
   -> agyis re decompile / disasm / xrefs (or REA procedure_assembly / xrefs)
   -> Pinpoint exact cmp/test/jne guard, enum tag, or struct field offset
                      |
                      v
[Step 4: Schema & Golden Fixture Remediation]
   -> Cross-check Vector 1 schema & Vector 2 golden stream for wire mismatch
   -> Update cleanroom spec, obligation ledger, and cleanroom codec
                      |
                      v
[Step 5: Automated Re-Verification]
   -> Run project-native test suite -> Run E2E harness -> Run agyis verify
```

### Common Binary & Wire Analysis Traps
1. **Scalar Width, Signedness & Type-Tag Mismatches**: Encoding an 8-byte integer in a 4-byte field group (or swapping signed/unsigned or endianness) corrupts downstream framing offsets and causes silent parser rejection. Catch with Vector 1 schema tests.
2. **Ciphertext Replay in Plaintext Sessions**: Replaying raw captured bytes from an encrypted session into an unencrypted test stream injects invalid opcodes and triggers immediate peer teardown. Verify encryption state before carving Vector 2 fixtures.
3. **Blocking Serial Socket I/O During Settle Delays**: Sleeping on a single-threaded read/write loop while waiting for peer initialization leaves incoming control or heartbeat frames unread, causing TCP buffer starvation and timeouts. Decouple async read and write loops.
4. **Ghidra Leading-Dot Path & Orphan Lock Hazards**: Passing leading-dot paths directly causes Ghidra headless rejection; crashed analyzers leave `*.lock` files that block read-only mounts. Always resolve a non-dot Ghidra project path (or `.dirtyroom/dirtyroom.env` `REA_GHIDRA_PROJECT_DIR`) and clear stale locks with `agyis re clean --locks`.
5. **Context Flood from Unbounded Disassembly Dumps**: Always default REA MCP tools to `detail: "summary"`, bound `agyis re disasm --limit` and `agyis re find --limit`, and paginate large analysis views via `inspect_analysis_view`.

---

## 6. Cleanroom Verification Gates and Obligation Ledgers

Under **PSL-RE-001 §3**, cleanroom claims must be backed by machine-verifiable ledgers in `.agents/ledger/obligation_ledger.json` and specification documents in `docs/specs/**` containing zero executable or copied vendor code.

### 6.1 Obligation Ledger & Residual Unknowns Lifecycle
- **Scaffold Ledger**: Generate an REA 6.9.0 typed obligation ledger template:
  ```bash
  agyis verify --scaffold
  ```
- **Bind Immutable Evidence**: Every reviewed obligation must cite concrete evidence record IDs (`review_evidence_ids`), `manifest.bindings` entries, provider metadata (`ghidra`, `tshark`, `objdump`), and SHA-256 digests (`evidence_bundle.records`) rather than ungrounded prose.
- **Track Residual Unknowns (`PSL-INV-002`)**: Record unresolved behavioral questions with `record_unknown`, inspect open heads via `list_unknowns`, and close them exclusively through `verify_unknown_resolution` backed by observed evidence.

### 6.2 Mandatory Verification Commands
```bash
# Verify docs/specs/** contains zero executable code leaks and clear spec_dirty fence
agyis verify --spec

# Formally validate .agents/ledger/obligation_ledger.json against evidence
agyis verify

# Direct upstream REA verification gates (when REA CLI is installed)
rea verify-reconstruction
rea evaluate-coverage
```

---

## 7. References and Layer Extensibility

- **Dirty-Room Operations Runbook**: `docs/runbooks/dirtyroom-operations.md` (in `agyis-harness`) — End-to-end preparation, seeding, priming, maintenance, and troubleshooting matrix.
- **REA Native Architecture Specification**: `docs/official-specs/rea-antigravity-architecture.md` (in `agyis-harness`) — `PSL-SPEC-2026-REA-001` covering the 255 MCP tools (`rea@6.9.0`), CLI commands, provider matrix, direct-mount benchmarks, and cleanroom contracts.
- **Upstream REA Dynamic Skill**: `reverse-engineer-anything` (provisioned dynamically via `agyis doctor --experimental-rea --heal` or `agyis init --experimental-rea`; never vendored in-tree).
- **3-Tier Skill Extensibility (Layer 1 vs. Layer 3)**: This `re-ops` skill is the target-agnostic **Layer 1** product skill distributed with `agyis-harness` (provisioned via `--role re`, `--role cleanroom`, or the `ops` skill group). Target-specific protocol constants, engine quirks, and workspace CLI extensions (`agyis ext`) belong exclusively in project-scoped **Layer 3** skills under `<workspace>/.agents/skills/` to preserve **ADR-014** Product vs. Project bifurcation.
