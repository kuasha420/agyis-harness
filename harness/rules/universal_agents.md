---
trigger: manual
description: Universal agent rules template for target workspace onboarding (PSL Invariant Codex v2)
---

<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Universal Empirical Agent Rules: PSL Invariant Codex v2

These operational rules govern cognitive behavior and human-in-the-loop alignment for software engineering projects powered by the **Agyis Harness**. Deterministic environment guarantees (CPython >= 3.12 runtime injection, pager normalization, surgical grep/diff exit sanitization, output compaction, and compaction runway advisories) are enforced transparently by harness hooks.

---

## 1. Explicit Project Command Dictionary (The Victory Pattern)

_Explicit CLI palettes yield 10x lower human intervention rates:_

```bash
# 🧪 Project Verification & Agyis Quality Gates
agyis test --diff                              # Run fast targeted tests for uncommitted changes
agyis test --full                              # Run complete project verification suite
agyis verify --spec                            # Verify cleanroom specifications in docs/specs/**
agyis verify                                   # Formally verify cleanroom obligations against evidence
agyis audit aff                                # Audit architectural fitness, boundary & cycle compliance

# 🩺 Environment Diagnostics, Auto-Healing & Hygiene
agyis doctor                                   # Audit 3-tier runtime matrix, hooks & DB port collisions
agyis status                                   # Print harness health, active hooks, horizon & telemetry
agyis clean                                    # Clean stale checkpoints, dead worktrees & scratchpads

# 🧩 Skills, Rules, Subagents & Cockpit Routing
agyis skills                                   # List installed modular skills & stack triggers
agyis rules --lint                             # Lint workspace skills and personas for rule echoes
agyis agents                                   # List registered specialist subagents & bundles
agyis agents validate --json                   # Validate <=20 tool ceiling and canonical v2.34+ tools
agyis subagents --liveness                     # Inspect active subagents & heartbeat liveness
agyis cockpit status                           # Print flight deck status, runway tokens & git state
agyis router <workflow>                        # Display dynamic subagent router briefing & payload
agyis checkpoint status                        # Check pre-compaction state capture & horizon status

# 🌐 Remote Operations & Empirical Telemetry
agyis remote exec <target> "<cmd>"             # Multiplexed SSH with login-shell promotion
agyis remote script <target> <file>            # Stdin script streaming (zero disk footprint)
agyis remote triage <target>                   # Compact (<2KB) multi-component health report
agyis sync                                     # Bi-directional telemetry synchronization
```

---

## 2. Empirical Verification & Clean-Room Testing (PSL-INV-001)

1. **Mandatory Native Verification**:
   - Execute the active repository's native verification command (`pnpm test`, `cargo test`, `pytest`, `go test`, `make test`, or `./agyis test` inside `agyis-harness`) after the final edit and assert exit code 0 before declaring any task "complete", "fixed", or "verified".
2. **Hermetic Isolation & Authentic Tests**:
   - Component tests must run rapidly and hermetically using `tempfile.TemporaryDirectory()` and in-memory mocks rather than external networks, unbounded sleeps, or product logic duplicated in assertions.
3. **Mandatory Build Cache Invalidation**:
   - Purge stale build caches (`.next/`, `.turbo/`, `node_modules/.cache`) prior to verification gates in multi-branch PR rebase, migration, or onboarding workflows.

---

## 3. Epistemic Honesty & Observed Evidence (PSL-INV-002)

1. **Observed-Only Reporting**:
   - State as fact only file paths, symbol names, implemented behavior, and test/command outputs directly observed in files read/written or tool output; mark inferences explicitly as inferred.
2. **Truthful Scope & Residual Unknowns**:
   - State exact scopes and failures of mocked or filtered runs instead of reporting them as full passes; never extrapolate unprinted fields, counts, or timings, and track residual unknowns explicitly with required authorities.

---

## 4. Tool Determinism, Failure Transparency & Minimal Diffs (PSL-INV-003)

1. **Zero Error Swallowing & Pattern Probing Exception**:
   - Ban bare `except:`, `except Exception: pass`, and masked pipeline exits in production code; standalone terminal probes (`grep`, `rg`, `diff`) without conditionals append `|| [ $? -eq 1 ]` to handle benign empty matches cleanly.
2. **Pre-Flight Checks, Scratch Scripts & Surgical Edits**:
   - Verify required binaries (`command -v <bin>`), bound noisy outputs, place multi-line scripts in `scratch/*.py` or `scratch/*.sh`, and apply surgical contiguous edits (`edit_file`) preserving unrelated comments and docstrings.
3. **Automated Database Port Collision Remediation**:
   - Resolve container DB port 5432 collisions via automated discovery and rebinding (`detect_port_collision.py --find-free --rebind --env .env`) instead of killing unrelated host services.

---

## 5. Context Signal Hygiene & Runway Discipline (PSL-INV-004)

1. **512k/1M Context Runway & 80-Step Soft Epoch Horizon**:
   - Monitor context consumption proportionally across `512k`/`1M` windows: converge deliverables around `~70%` (amber), generate `.agents/artifacts/checkpoints/<conversation_id>.md` via `agyis checkpoint generate` at `~90%` (red), and honor the `80`-step soft epoch advisory (`SOFT_EPOCH_STEP_ADVISORY = 80`).
2. **Anti-Loop, Reactive Wait & Single-Source Hygiene**:
   - Never repeat identical `read_file` slices or search queries, never poll `manage_task(Action='status')` or tail task logs (await reactive wakeup), keep `.agents/` skills/rules/agents single-sourced via symlinks, exhaust native CLI flags before monkeypatching, and delegate broad sweeps to isolated workers (`workspace:"share"` or `"branch"`).

---

## 6. Risk-Scaled Planning & Human Steering (PSL-INV-005)

1. **Blast-Radius-Scaled Planning & Plan Anchoring**:
   - Crystallize multi-component designs into an interactive `implementation_plan.md` artifact (high resolution for active work, medium for near-term milestones, low for far-future scope) and anchor implementation decisions to the agreed plan.
2. **Confirmation Gates, Two-Failure Escalation & Milestone Compaction**:
   - Pause for explicit confirmation before destructive operations (`git reset --hard`, force-push, deletions, reboots). If an approach fails twice consecutively, stop thrashing, report concisely, and propose options; compact milestones into project ledgers (`<50` lines), commit clean changes, and recommend a fresh session reset.

---

## 7. Independent Verification & Subagent Governance (PSL-INV-006)

1. **Author != Verifier & Zero Coordinator Code Thrash**:
   - Code authors never self-certify; multi-phase deliverables traverse independent review (`@agyis_reviewer` + `@agyis_auditor`) on committed revisions while coordinators orchestrate via typed transition payloads without mutating product code directly.
2. **Tool Ceiling & Truthful Delegate Liveness**:
   - Agent definitions must declare `<=20` valid `v2.34+` tools (never obsolete v1 or static MCP names); verify delegate heartbeats via `agyis subagents --liveness` before reporting progress.

---

## 8. Live Reality Over Static Fakes (PSL-INV-007)

1. **Dynamic Lifecycle & Route Synchronization**:
   - Never fake dynamic runtime views with static snapshots; track active SPA routes (`/c/:id` and split views), purge stale DOM nodes/styles/singletons on re-mount, and test multi-session switching and API fallback paths across distinct fixtures.

---

## 9. Architectural Fitness & Sovereign Boundaries (PSL-INV-008)

1. **Structural Governance (`ADR-014`)**:
   - Satisfy automated fitness gates (`agyis audit aff` `<0.25s`, `100/100` score), enforce strict layer boundaries (`harness/` vs `pipeline/`) with zero proprietary IP or secret leaks, externalize non-native assets into `assets/` via `importlib.resources`, cap in-memory caches, and keep import graphs strictly acyclic (DAG).

---

> **On-Demand Domain Pack — Cleanroom RE & Pre-Analyzed Ghidra Cache (`PSL-RE-001`)**: For binary reverse engineering, disassembly/decompilation, or cleanroom reconstruction, load `re-ops` (`harness/skills/re-ops/SKILL.md`) for `.dirtyroom/` quarantine, `rea@6.9.0` obligation ledgers, and `-noanalysis -readOnly` cache rules.
