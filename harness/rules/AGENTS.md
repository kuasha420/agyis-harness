<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Empirical Agent Rules: Agyis Harness Guidelines

These operational rules govern cognitive behavior and human-in-the-loop alignment for **agyis-harness** (formerly `psl-agy-harness`). All deterministic environment guarantees (CPython >= 3.12 runtime injection, pager normalization, surgical grep exit sanitization, output compaction) are enforced transparently by harness hooks.

---

## 1. Explicit Project Command Dictionary (The Victory Pattern)
*Derived from purrmission & sunshine-physio: explicit CLI palettes yield 10x lower human intervention rates:*

```bash
# 🧪 Verification & Testing (Hermetic, 1,065 tests, clean dots)
./agyis test                                   # Run complete project test suite (<25s suite, sub-second components)
python3 -m harness.cli test                    # Run complete project test suite
agyis verify --spec                            # Verify cleanroom specifications in docs/specs/**
agyis verify                                   # Formally verify typed cleanroom obligations against evidence
python3 -m unittest discover -s tests -v        # Standard unittest runner

# 🩺 Environment Diagnostics, Auto-Healing & Port Collision
agyis doctor                                   # Audit 3-tier runtime matrix & port 5432 collisions
agyis doctor --heal                            # Safe zero-sudo user-space repair
agyis status                                   # Print harness health, active hooks, attention horizon & telemetry
python3 harness/skills/db-ops/scripts/detect_port_collision.py --find-free --rebind --env .env # Auto-rebind DB port collision

# 🚀 Turnkey Workspace Onboarding & Scaffolding
agyis onboard [path] [flags]                   # Golden path onboarding (branch isolation, cache purge, PR delivery)
agyis onboard . --create-branch chore/onboard  # Onboard target repository in isolated git branch
agyis onboard . --allow-dirty                  # Proceed safely on dirty tree with pre-onboard safety patch
agyis onboard . --skills db-ops,remote-ops     # Explicitly provision specialist skills override
agyis init [path] [-s <stack>] [-r <role>]     # Initialize workspace project with stack skills & cleanroom ledgers
agyis harmonize [path] [--dry-run]             # Harmonize legacy .agent/ directories into modern .agents/

# 🪝 Lifecycle Hooks Dispatcher
python3 -m harness.cli hook command-safety     # PreToolUse terminal safety guard
python3 -m harness.cli hook anti-loop          # PreToolUse redundant call breaker
python3 -m harness.cli hook compactor          # PostToolUse 2KB output compactor
python3 -m harness.cli hook anti-drift         # PreToolUse plan boundary and auditor write guard
python3 -m harness.cli hook token-proximity-guard # PreToolUse attention horizon token guard
python3 -m harness.cli hook completion-fence   # Stop gate verification fence (code_dirty vs spec_dirty)

# 📊 Empirical Telemetry Laboratory & Background Daemon
./agyis sync                                   # Audit & synchronize active session into telemetry.db
agyis sync --service install                   # Install background telemetry systemd user daemon (ADR-030)
agyis sync --service status                    # Check background telemetry sync daemon status
agyis sync --service start                     # Start background telemetry sync daemon
agyis sync --service stop                      # Stop background telemetry sync daemon
./agyis audit deep                             # Dissect 30 titan sessions (>=1k steps) & Knot inception
./agyis audit volume                           # Analyze tool & command volume distributions
python3 -m harness.cli audit all               # Run full extraction, classification & summary
python3 -m harness.cli audit extract           # Ingest ~/.gemini/antigravity transcripts to telemetry.db
python3 -m harness.cli audit classify          # Categorize trajectories into WHAT_WORKED / WHAT_FAILED
python3 -m harness.cli audit inventory         # Catalog plugins, skills, hooks & MCP servers

# 🧩 Skills & Subagents Discovery & Deduplication
agyis skills                                   # List installed modular skills & triggers
agyis skills --prune-duplicates                # Prune redundant workspace skills shadowing global plugin (~4,500 tokens/turn saved)
agyis skills --prune-duplicates --dry-run      # Preview duplicate skill pruning without mutating disk
agyis agents                                   # List registered specialist subagents & tools
agyis subagents [--json]                       # Live active subagents status table & context health gauges (<2ms query)

# 🖥️ Electron GUI DevTools & Trajectory Debugging (ADR-014)
agyis gui                                      # Unlock Trajectory Debug View via live CDP WebSocket
agyis gui --devtools                           # Inspect DevToolsActivePort and print Chrome Inspect URLs
agyis gui --no-popup                           # Prime DevTools flags and hotkeys (F12, Ctrl+Shift+T) without auto-popup
agyis gui --toggle                             # Toggle Trajectory Debug View open/closed

# 🧹 Multi-Branch Workspace & Cache Hygiene
rm -rf .next/ .turbo/ node_modules/.cache      # Invalidate stale build caches prior to verification gates
python3 -c "from harness.delivery import purge_build_caches; purge_build_caches('.')" # Standalone cache purge

# 🛠️ Workstation & Remote Modular Skills
# storage-ops:      Bounded disk triage (`du -h -d 1`), pacman cache (`paccache -r`), journalctl vacuum, Docker prune, Btrfs, ntfs3
# audio-ops:        PipeWire/WirePlumber user diagnostics (`wpctl status`), sink recovery, bluetoothctl, loudnorm, VLC split-package
# display-ops:      Wayland probe (`kscreen-doctor -o`), portal restart (no -9), Electron Ozone/PipeWire flags, Sunshine KMS capture
# sec-forensics:    Ephemeral RO triage (`docker run --rm -v /:/host:ro`), cloud key revocation, remote script streaming, PDF
# media-ops:        yt-dlp stream acquisition ladder (`--impersonate chrome`), ffmpeg flips/rotations, hardware acceleration probe
# db-ops:           Non-interactive psql/sqlite3 CLI, connection pool saturation, locks, WAL checkpoints, Docker DB triage
# mesh-ops:         Knot hardware mesh coordination, Tailscale/WireGuard ping, ControlMaster sockets, state sync, KDE Connect
# git-worktree-ops: Isolated worktree lifecycle, branch cleanup, orphan prune, stash hygiene, index.lock recovery

# 🌐 Remote Operations & Cloud/Mesh Triage (ADR-027)
agyis remote exec <target> "<cmd>"             # Multiplexed SSH with login-shell promotion
agyis remote script <target> <file>            # Stdin script streaming (zero disk footprint)
agyis remote script <target> <file> --stage    # Staged execution with trap cleanup
agyis remote triage <target>                   # Compact (<2KB) multi-component health report
agyis remote socket status                     # List active OpenSSH ControlMaster sockets
agyis remote socket cleanup                    # Remove active ControlMaster sockets

# 🔬 REA & Cleanroom Reconstruction Tooling (ADR-028)
rea --version                                  # Report REA CLI & SDK version (6.5.0 / 2.3.1)
rea mcp doctor                                 # Audit REA stdio MCP catalog & checksums
rea providers --json                           # List available disassembler engines (opt-in deep probe)
rea verify-reconstruction                      # Formally verify typed cleanroom obligations against evidence
rea evaluate-coverage                          # Calculate reconstruction coverage against obligation ledger
agyis verify --spec                            # Verify cleanroom specifications in docs/specs/**
agyis doctor --experimental-rea                # Audit REA providers, JDK 21+, Ghidra & MCP registration
agyis doctor --experimental-rea --heal         # Safe zero-sudo auto-healing & REA skill provisioning
```

---

## 2. Product vs. Project Bifurcation (ADR-014)
- **The Product (`harness/`)**:
  - The distributable extension harness plugin and CLI toolchain.
  - Zero-dependency, hermetic, clean contracts (`matrix.json`, `hooks.json`, CLI).
  - NEVER place scratch files, one-off scripts, or local telemetry databases inside `harness/`.
- **The Project (`pipeline/`, `data/`, `tests/`, `docs/`)**:
  - The development repository, empirical telemetry laboratory (`data/telemetry.db`), research taxonomy ledgers, and test suites.

---

## 3. Clean-Room Testing & Verification Contract (ADR-015)
1. **Mandatory Automated Verification**:
   - Never declare a task "complete", "fixed", or "verified" without executing `python3 -m harness.cli test` and asserting exit code 0.
2. **Sub-Second Benchmark Invariant**:
   - Individual unit and contract test modules must execute in sub-second benchmark latency (<1.0 second benchmark, <0.02s–0.75s). Slow operations, unbounded sleeps, or unneeded whole-filesystem sweeps are strictly prohibited in verification loops.
3. **Hermetic Isolation**:
   - Tests must never access the network or depend on external daemon services.
   - All state-persisting components must support `PSL_HARNESS_STATE_DIR` and use `tempfile.TemporaryDirectory()`.
4. **Mandatory Build Cache Invalidation**:
   - Prior to executing verification gates (`python3 -m harness.cli test`, `pnpm test`, `cargo test`) in multi-branch PR rebase, migration, or onboarding workflows, stale build caches (`.next/`, `.turbo/`, `node_modules/.cache`) MUST be purged to prevent phantom build artifact regressions.

---

## 4. Terminal Invariants & Grep Probing Exception (ADR-013)
1. **Pre-flight Tool Availability (Mitigate Exit Code 127)**:
   - Verify availability (`command -v <bin>`) or handle fallback paths gracefully.
2. **Context Flood Prevention (The 200+ Step Cliff)**:
   - Never execute unfiltered commands that dump thousands of lines. Pipe large outputs through `head -n <N>`, `tail -n <N>`, or `wc -l`.
3. **Pattern Probing Exception**:
   - Error swallowing is banned in production code, but standalone terminal pattern probes (`grep`, `diff`) without conditionals must use `|| [ $? -eq 1 ]` to avoid panicking on benign empty matches.
4. **Multi-line Script Hygiene**:
   - Write multi-line Python scripts to `<artifactDir>/scratch/script.py` rather than escaping complex bash `-c` one-liners.
5. **Automated Database Port Collision Remediation**:
   - When containerized services or database migrations fail with port binding or connection pool errors (e.g. Prisma P1000 on port 5432 occupied by foreign containers), execute automated collision discovery and rebinding (`python3 harness/skills/db-ops/scripts/detect_port_collision.py --find-free --rebind --env .env`) rather than manually terminating unrelated host processes.

---

## 5. Surgical Contiguous Edits Invariant (99.9% Tool Success)
*Audit revealed replace_file_content achieved 99.9% success (only 4 failures out of 4,650 calls):*
1. Always make single contiguous block replacements for targeted edits.
2. Do NOT overwrite whole files when modifying specific functions or blocks.
3. Preserve surrounding comments, docstrings, and formatting.

---

## 6. Context Preservation & Subagent Ladder
*Trajectories <50 steps / <50k tokens maintain 0.8 errors/session; >200 steps suffer a 20x error spike:*
1. **Keep Primary Context in the Healthy Zone (<50k tokens)**.
2. **Anti-Loop Heuristics**:
   - Do NOT repeatedly call `view_file` on the same file within consecutive steps.
   - Evolve search queries; do not repeat identical `grep_search` patterns.
   - **Strict Reactive Wait Invariant**: Never poll `manage_task(Action='status')` NOR repeatedly read background task logs (`tail`, `cat`, `grep`, `view_file` on `.system_generated/tasks/*.log`) to print manual progress updates. After launching a background task, output a single concise notification and stop calling tools. Await reactive wakeup.
3. **Tool-Native Primacy (The Anti-Premature-Cognition Invariant)**:
   - When an external CLI or tool fails, exhaust the tool's standard native options, configurations, and flag escalation ladders (e.g., `--impersonate`, `--concurrent-fragments`, retry/timeout flags, native formatting options) before reading internal tool source code, monkeypatching APIs, or constructing custom proxy scripts. Cognitive intervention is a last resort, not a first reflex.
4. **Single-Source Skill Deduplication Invariant**:
   - Never duplicate global plugin skills inside workspace-local `.agents/skills/` without specialized modifications. Duplicate skills bleed ~4,500 tokens/turn of redundant prompt context into every turn. Enforce single-source hygiene via `agyis skills --prune-duplicates` and strictly respect the 3-tier boundary (Layer 3: Project Specialist > Layer 2: User Environment > Layer 1: Global Plugin).
5. **Subagent Delegation Protocol**:
   - For multi-phase refactoring, test debugging, or massive build sweeps, delegate to subagents in shared worktrees (`Workspace: "share"`).

---

## 7. The Artifact-First Planning Invariant (ADR-012) & Dynamic Aperture
1. **Anti-Chatbot Seduction**:
   - Never propose multi-component architectural changes or execution plans in raw conversational chat turns.
   - All non-trivial proposals must immediately crystallize into an interactive `implementation_plan.md` artifact before requesting operator confirmation.
2. **Dynamic Sliding Aperture**:
   - High resolution for current task execution.
   - Medium resolution for near-future milestones (macro boundaries; no speculative code).
   - Low resolution for far-future vision.
3. **Retroactive Horizon Compaction**:
   - When completing a phase or milestone, compact findings into `docs/taxonomy/project-ledger.md` under 50 lines, update `roadmap.md`, commit clean code to git, and instruct the operator to reset session.

---

## 8. Human-in-the-Loop & Steering Alignment
1. **Anti-Drift Commitment**: Anchor all implementation decisions to the agreed plan. If novel obstacles arise, pause and present options.
2. **Proactive Confirmation Gates**: When encountering destructive operations (file deletion, git branch force-push, node reboots), pause for explicit review.
3. **Clear Error Reporting**: If a command fails twice, stop thrashing. State the error concisely and propose a concrete path forward.

---

## 9. Cleanroom Reverse Engineering & Reconstruction Invariants (ADR-028)
1. **Dirty Room vs. Clean Room Separation**:
   - Maintain a strict boundary between binary inspection and cleanroom specification/implementation authoring.
   - All disassembler execution, decompiler output inspection, and dynamic tracing (`.rea/**`, `decompiled/**`, `artifacts/rea/**`) occur strictly within the Dirty Room.
   - Cleanroom specifications (`docs/specs/**`) and reconstructed source code are authored strictly within the Clean Room. Never copy decompiler output, proprietary strings, or raw binary artifacts into clean implementations.
2. **Typed Obligation Ledgers (`.agents/ledger/**`)**:
   - Reconstructions must derive from formal specifications backed by typed obligation ledgers (`.agents/ledger/obligations.json`).
   - Retain immutable evidence records (`evidence_id`, subject, provider, digest) in `.agents/ledger/evidence_bundle.json`.
   - Formal manifest clearance (`.agents/ledger/manifest.json`) requires a valid JSON schema with `"status": "verified"`, a 64-character SHA-256 `evidence_hash`, and all obligations marked `"satisfied"`.
3. **Residual Unknowns Lifecycle**:
   - Unresolved ambiguities, unobserved code paths, and missing specification authorities must be formally tracked using `record_unknown` and `list_unknowns`.
   - Unknowns may only be transitioned to resolved via `verify_unknown_resolution` citing concrete, observed `evidence_id`s. Guessing, assuming, or silently dropping unknowns is strictly prohibited.
4. **Formal Verification Before Exit**:
   - Editing cleanroom specifications (`docs/specs/**`) or obligation ledgers (`.agents/ledger/**`) marks `spec_dirty = True`.
   - The completion fence blocks termination until verified via `rea verify-reconstruction`, `rea evaluate-coverage`, `agyis verify --spec`, or a verified `manifest.json`.

