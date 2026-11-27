---
trigger: manual
description: Universal agent rules template for target workspace onboarding (PSL Invariant Codex v2)
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

> Inherits universal invariants PSL-INV-001 through PSL-INV-008 from the active global Agyis plugin rules.

## Explicit Project Command Dictionary

_Explicit CLI palettes yield 10x lower human intervention rates:_

```bash
# ◆ Project Verification & Agyis Quality Gates
agyis test --diff                              # Run fast targeted tests for uncommitted changes
agyis test --full                              # Run complete project verification suite
agyis verify --spec                            # Verify cleanroom specifications in docs/specs/**
agyis verify                                   # Formally verify cleanroom obligations against evidence
agyis audit aff                                # Audit architectural fitness, boundary & cycle compliance

# ◆ Environment Diagnostics, Auto-Healing & Hygiene
agyis doctor                                   # Audit 3-tier runtime matrix, hooks & DB port collisions
agyis status                                   # Print harness health, active hooks, horizon & telemetry
agyis clean                                    # Clean stale checkpoints, dead worktrees & scratchpads

# ◆ Skills, Rules, Subagents & Cockpit Routing
agyis skills                                   # List installed modular skills & stack triggers
agyis rules --lint                             # Lint workspace skills and personas for rule echoes
agyis agents                                   # List registered specialist subagents & bundles
agyis agents validate --json                   # Validate <=20 tool ceiling and canonical v2.34+ tools
agyis subagents --liveness                     # Inspect active subagents & heartbeat liveness
agyis cockpit status                           # Print flight deck status, runway tokens & git state
agyis router <workflow>                        # Display dynamic subagent router briefing & payload
agyis checkpoint status                        # Check pre-compaction state capture & horizon status

# ◆ Remote Operations & Empirical Telemetry
agyis remote exec <target> "<cmd>"             # Multiplexed SSH with login-shell promotion
agyis remote script <target> <file>            # Stdin script streaming (zero disk footprint)
agyis remote triage <target>                   # Compact (<2KB) multi-component health report
agyis sync                                     # Bi-directional telemetry synchronization
```
