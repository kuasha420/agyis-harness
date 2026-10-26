<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

<!-- Inherits Universal Invariants from Global Plugin: PSL-INV-001 through PSL-INV-008 -->

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

# 🛫 Cockpit Flight Director & Subagent Router (PSL-SPEC-2026-COCKPIT-DIRECTOR-001)
agyis cockpit status                           # Print flight deck health, tokens, active subagents & git state
agyis cockpit route <letter|alias>             # Print dispatch briefing & transition payload (e.g. agyis cockpit route A / rca)
agyis cockpit verify [--allow-dirty]           # Audit active session against the 5 flight director invariants
agyis router <letter|alias>                    # Dynamic subagent router CLI alias (e.g. agyis router victory)
agyis ladder <letter|alias>                    # Backwards-compatible router CLI alias (e.g. agyis ladder builder)

# 🧹 Multi-Branch Workspace & Cache Hygiene
rm -rf .next/ .turbo/ node_modules/.cache      # Invalidate stale build caches prior to verification gates
python3 -c "from harness.delivery import purge_build_caches; purge_build_caches('.')" # Standalone cache purge

# 🛠️ Workstation & Remote Modular Skills
# cockpit-director: Air Traffic Control Tower runbook, root flight deck pairing, 12 routing workflows, compaction thresholds
# subagent-router:  Dynamic subagent routing, 12 workflows, 4 execution modes (Ladder, Fan-Out, Teamwork, Boost), swarm PRs
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

