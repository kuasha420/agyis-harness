---
trigger: manual
description: Universal agent rules template for target workspace onboarding
---

<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Universal Empirical Agent Rules: Agyis Harness Guidelines

These operational rules govern cognitive behavior and human-in-the-loop alignment for software engineering projects powered by the **Agyis Harness**. All deterministic environment guarantees (runtime injection, pager normalization, surgical grep exit sanitization, output compaction, compaction runway advisories) are enforced transparently by harness hooks.

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

## 2. Universal Automated Verification Standard (PSL-INV-001)

1. **Mandatory Project-Native Automated Verification**:
   - Always execute the active repository's native verification command (`pnpm test`, `cargo test`, `pytest`, `go test`, `make test`, or `./agyis test` inside `agyis-harness`) before declaring a task "complete", "fixed", or "verified". Assert exit code 0.
2. **Fast & Hermetic Test Hygiene**:
   - Component unit and contract tests must execute cleanly and hermetically without slow network calls, unbounded sleeps, or whole-filesystem sweeps in verification loops.
3. **Hermetic Isolation & Authentic Assertions**:
   - Tests must use temporary directories and hermetic mocks rather than untracked external services or real product homework re-implemented in assertions.
4. **Mandatory Build Cache Invalidation**:
   - Prior to executing verification gates in rebase, migration, or onboarding workflows, purge stale build caches (`.next/`, `.turbo/`, `node_modules/.cache`) to prevent phantom build artifact regressions.

---

## 3. Terminal Invariants & Grep Probing Exception (PSL-INV-002)

1. **Pre-flight Tool Availability (Mitigate Exit Code 127)**:
   - Verify tool availability (`command -v <bin>`) or handle fallback paths gracefully.
2. **Context Flood Prevention**:
   - Never execute unfiltered commands that dump thousands of lines. Pipe large outputs through `head -n <N>`, `tail -n <N>`, or `wc -l`.
3. **Zero Error Swallowing & Pattern Probing Exception**:
   - Error swallowing (bare `except:`, silent pipe failures without `set -euo pipefail`) is banned in production code; standalone terminal probes (`grep`, `diff`) without conditionals must append `|| [ $? -eq 1 ]` to handle benign empty matches cleanly.
4. **Multi-line Script Hygiene**:
   - Write multi-line scripts to temporary scratch files (`scratch/script.sh` or `scratch/script.py`) rather than escaping fragile multi-line `bash -c` one-liners.
5. **Automated Database Port Collision Remediation**:
   - When containerized DB services hit port 5432 collisions, use automated discovery and rebinding (`detect_port_collision.py --find-free --rebind --env .env`) rather than killing unrelated host services.

---

## 4. Surgical Contiguous Edits Invariant (PSL-INV-003)

1. Always make single contiguous block replacements for targeted edits (`replace_file_content`).
2. Do NOT overwrite whole files when modifying specific functions, classes, or blocks.
3. Preserve surrounding comments, docstrings, imports, and formatting.

---

## 5. Context Preservation, Dynamic Runway & Subagent Delegation (PSL-INV-004)

1. **256k Context Runway & 80-Step Soft Epoch Horizon Model**:
   - Monitor the **256,000-token** context window carefully:
     - **`180,000` tokens (Amber)**: Approaching critical runway limit; focus on converging active deliverables.
     - **`230,000` tokens (Red / Compaction Trigger)**: Compaction imminent (~245,941 historical average trigger); emit or update `.agents/artifacts/checkpoints/<conversation_id>.md` via `agyis checkpoint generate` before handoff.
     - **Soft Epoch Horizon (Per-Epoch Soft Budget = 80 steps)**: `SOFT_EPOCH_STEP_ADVISORY = 80` emits a non-blocking convergence advisory after 80 steps in the current epoch; open sweeps and in-flight edits remain allowed.
2. **Anti-Loop & Reactive Wait Discipline**:
   - Do NOT repeatedly call `view_file` on the same file within consecutive steps.
   - Evolve search queries; do not repeat identical `grep_search` patterns.
   - Never poll `manage_task(Action='status')` or repeatedly tail task logs; output one concise update and await reactive wakeup.
3. **Tool-Native Primacy & Single-Source Skill Hygiene**:
   - Exhaust native CLI flags/options before reading internal tool source or monkeypatching, and avoid duplicating global plugin skills in `.agents/skills/` without project-specific customization.
4. **Subagent Delegation Protocol**:
   - Decompose multi-phase refactoring, test debugging, or broad sweeps using `agyis_*` personas (`@agyis_investigator`, `@agyis_planner`, `@agyis_builder`, `@agyis_reviewer`, `@agyis_custodian`, `@agyis_auditor`, `@agyis_coordinator`, `@agyis_architect`) across the canonical lifecycle (`Investigator / Planner -> Builder -> Reviewer -> Custodian -> Auditor -> Coordinator`) inside isolated worktrees (`Workspace: "share"` or `"branch"`).

---

## 6. Artifact-First Planning Invariant & Dynamic Aperture (PSL-INV-005)

1. **Anti-Chatbot Seduction**:
   - Never propose multi-component architectural changes in raw chat; crystallize non-trivial designs into an interactive `implementation_plan.md` artifact before requesting operator confirmation.
2. **Dynamic Sliding Aperture**:
   - Maintain high resolution for active execution, medium resolution for near-term milestones, and low resolution for far-future scope.
3. **Retroactive Horizon Compaction**:
   - Compact completed phase findings into the project ledger, update the roadmap, commit clean changes, and instruct the operator to reset into a fresh session.

---

## 7. Human-in-the-Loop & Steering Alignment (PSL-INV-006)

1. **Anti-Drift Commitment**: Anchor implementation decisions to the agreed plan and pause when unforeseen blockers or ambiguity arise.
2. **Proactive Confirmation Gates**: Pause for explicit review before destructive operations (file deletion, force-push, service restarts/reboots).
3. **Clear Error Reporting & Complete Deliveries**: Deliver complete packages (code + types + tests + docs). If a command fails twice, stop thrashing, state the error concisely, and propose concrete next options.

---

## 8. Universal Cleanroom Reverse Engineering & Reconstruction Invariants (PSL-INV-007)

1. **Dirty Room vs. Clean Room Isolation**: Keep binary/disassembly inspection (`.dirtyroom/`) strictly isolated from cleanroom specifications and source authoring.
2. **Obligation Ledgers & Immutable Evidence**: Back cleanroom reconstructions with formal specifications, typed obligation ledgers, and immutable evidence digests.
3. **Residual Unknowns Lifecycle**: Track unresolved structures formally with required authorities; never fill gaps with silent assumptions.
4. **Formal Cleanroom Verification**: Evaluate obligation coverage (`agyis verify`) before closing cleanroom work.

---

## 9. Cockpit Flight Direction & Dual-Auditor Gate (PSL-INV-008)

1. **Zero-Code-Thrash Flight Direction**: Root orchestration (`@agyis_coordinator`) decomposes milestones, evaluates trade-offs, and enforces governance via structured transition payloads (`mission_id`, `objective`, `deliverables`, `context_paths`, `verification_gate`).
2. **Dual-Plane Communication & Dual-Auditor Gate**: Keep parent cockpit pairing distinct from child subagent `send_message` reporting, and pass multi-phase tasks through independent review (`@agyis_reviewer` + `@agyis_auditor`).

---

## 10. Pre-Analyzed Decompiler Cache Invariant (PSL-INV-009)

1. **Mandatory Pre-Analyzed Cache**: Never trigger unbounded full-binary Ghidra analysis passes during ad-hoc tool calls on binaries `>10 MB`; use pre-analyzed read-only project caches (`-noanalysis -readOnly`) returning queries in `<2.0s` while keeping `.dirtyroom/`, `.gpr`, and `.rep` files gitignored.

---

## 11. Anti-Vibe-Coding & Dynamic Lifecycle Invariant (PSL-INV-010)

1. **Live State & Route Synchronization**: Never fake dynamic runtime views with static snapshots; track active SPA routes, purge stale DOM nodes/singletons on re-mount, and verify multi-session switching and API fallback paths in tests.

---

## 12. Universal Architectural Fitness Invariant (PSL-INV-011)

1. **Structural Governance**: Satisfy automated fitness gates (`agyis audit aff`), enforce strict layer boundaries (core library vs. workspace pipelines), extract large embedded foreign-language assets into `assets/`, bound in-memory cache sizes, and maintain a strictly acyclic import graph (DAG).
