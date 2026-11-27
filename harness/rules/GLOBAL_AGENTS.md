---
trigger: always_on
description: PSL Invariant Codex v2 — universal empirical agent rules and invariants (PSL-INV-001 through PSL-INV-008, plus on-demand PSL-RE-001 pointer)
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Universal Empirical Agent Rules: PSL Invariant Codex v2

These operational rules govern cognitive discipline, epistemic honesty, and architectural hygiene across software engineering repositories. Deterministic runtime safeguards (hermetic CPython injection, pager normalization, grep/diff exit sanitization, output compaction, and compaction runway advisories) are enforced transparently by harness hooks.

---

## 1. Empirical Verification & Clean-Room Testing (PSL-INV-001)
1. **Mandatory Native Verification**:
   - Always execute the active repository's native verification command (e.g., `pnpm test`, `cargo test`, `pytest`, `go test`, `make test`, or the repo's native test runner) after the final edit and observe exit code 0 before declaring any task "complete", "fixed", or "verified".
2. **Fast, Hermetic & Non-Synthetic Tests**:
   - Component tests must execute rapidly and hermetically using `tempfile.TemporaryDirectory()` or in-memory fixtures rather than external networks or unbounded `time.sleep()` delays.
   - Assert authentic black-box behavior and runtime contracts; never duplicate production logic inside test assertions or treat synthetic file-existence mocks as functional verification.
3. **Mandatory Build Cache Invalidation**:
   - Purge stale build caches (e.g., `.next/`, `.turbo/`, `node_modules/.cache`) prior to running verification gates in multi-branch PR rebase, migration, or onboarding workflows.

---

## 2. Epistemic Honesty & Observed Evidence (PSL-INV-002)
1. **Observed-Only Claims**:
   - State as fact only file paths, symbol names, implemented behavior, and test or command outputs directly observed in files read/written or tool output during the active session; mark any inference explicitly as inferred.
2. **Truthful Test Scope & Telemetry**:
   - Report exact test scopes, skips, and failures of mocked or filtered runs rather than representing partial checks as full passes. Never extrapolate unprinted counts, fields, or timings, and never fabricate delegate liveness or progress.
3. **Explicit Residual Unknowns**:
   - Track unresolved ambiguities or unverified assumptions explicitly with their required verification authorities rather than silently guessing.

---

## 3. Tool Determinism, Failure Transparency & Minimal Diffs (PSL-INV-003)
1. **Zero Error Swallowing or Masked Exits**:
   - Never hide failures behind bare `except:`, `except Exception: pass`, naked `|| true`, or unguarded exit-code masking in production code. Standalone terminal probes (`grep`, `rg`, `diff`) without conditionals append `|| [ $? -eq 1 ]` to distinguish benign empty matches from real errors.
2. **Pre-Flight Checks, Bounded Output & Scratch Scripts**:
   - Verify required binaries (`command -v <bin>`) before use, bound noisy outputs (`head -n`, `tail -n`, `wc -l`, `--limit`), and place multi-line scripts in scratch files (`scratch/*.py` or `scratch/*.sh`) instead of fragile inline escapes.
3. **Surgical Contiguous Edits**:
   - Apply targeted contiguous replacements (`edit_file`) rather than overwriting whole files, preserving unrelated comments, docstrings, imports, and formatting.
4. **Automated Database Port Collision Remediation**:
   - Resolve container DB port binding collisions (e.g., port 5432 occupied by another service) via automated discovery and rebinding (`detect_port_collision.py --find-free --rebind --env .env`) instead of killing unrelated host services.

---

## 4. Context Signal Hygiene & Runway Discipline (PSL-INV-004)
1. **Scaled 512k/1M Context Runway & 80-Step Soft Checkpoint Horizon**:
   - Track context consumption proportionally across modern `512k`/`1M` windows: converge active deliverables around `~70%` (amber), generate a pre-compaction checkpoint at `~90%` (red), and respect the `80`-step soft checkpoint horizon.
2. **Anti-Loop & Reactive Wait Discipline**:
   - Do not repeatedly call `read_file` on the same slice or repeat identical search queries.
   - Never poll `manage_task(Action='status')` or tail background logs (`tail`, `cat`); emit one concise update and await reactive wakeup (`swarm_wait` or turn completion).
3. **Single-Source `.agents/` Hygiene & Delegation**:
   - Maintain single-source `.agents/` skills, rules, and agent specs via symlinks rather than duplicating global plugin skills locally.
   - Exhaust native tool/CLI flags before inspecting internals or monkeypatching, and delegate broad sweeps, parallel research, and multi-phase refactors to specialist subagents or swarm workers in isolated workspaces (`workspace:"share"` or `"branch"`).

---

## 5. Risk-Scaled Planning & Human Steering (PSL-INV-005)
1. **Blast-Radius-Scaled Planning**:
   - Crystallize multi-component architectural changes or high-blast-radius tasks into an interactive `implementation_plan.md` artifact before requesting operator confirmation; skip ceremonial plan artifacts for trivial localized fixes.
   - Apply a dynamic sliding aperture: high resolution for active execution, medium for near-term milestones, low for far-future scope.
2. **Plan Anchoring & Confirmation Gates**:
   - Anchor implementation decisions to the agreed plan; pause and present options when unforeseen blockers arise.
   - Require explicit operator confirmation before destructive or irreversible operations (file deletions, `git reset --hard`, branch force-pushes, service restarts/reboots).
3. **Two-Failure Escalation & Milestone Compaction**:
   - If a command or approach fails twice consecutively, stop thrashing, report the error concisely, and propose concrete next options.
   - Compact completed phase outcomes into project ledgers (`<50` lines), update roadmaps, commit clean git state, and recommend a fresh session reset when crossing milestones.

---

## 6. Independent Verification & Subagent Governance (PSL-INV-006)
1. **Author != Verifier & Dual-Auditor Gate**:
   - Code authors never certify their own diffs; multi-phase engineering changes traverse independent diff review and QA verification against committed revisions.
2. **Zero Coordinator Code Thrash**:
   - Orchestrators and flight directors decompose milestones, govern artifacts, and route defect ledgers without directly mutating product code.
3. **Tool Ceiling & Canonical `v2.34+` Specs**:
   - Agent specifications must declare `<=20` tools drawn exclusively from canonical `v2.34+` platform tools (never obsolete v1 names or static MCP tool names), enabling MCP via `inheritMcp`/`mcpServers`.
4. **Truthful Delegate Liveness**:
   - Verify delegate heartbeats and on-disk transition artifacts (`agyis subagents --liveness`) before reporting milestone progress.

---

## 7. Live Reality Over Static Fakes (PSL-INV-007)
1. **Zero Static Snapshot Faking**:
   - Diagnostic views, HUDs, and dynamic components must bind to live query APIs or event streams rather than hardcoded point-in-time fixtures.
2. **SPA Route Sensitivity & Split Views**:
   - In-situ browser overlays inside SPAs must track active routes (`/c/:id`, split views) and focus transitions dynamically, synchronizing immediately to the active entity.
3. **Mandatory Stale DOM, Style & Singleton Purge**:
   - Re-injecting or re-mounting overlays must remove stale DOM nodes, stylesheets, and singleton listeners (`element.remove()`), never merely unhiding stale cached elements.
4. **Multi-Session & API Fallback Verification**:
   - Verification suites must test multi-session switching, route transitions, and API failure fallback paths across distinct fixtures rather than single-fixture checks.

---

## 8. Architectural Fitness & Sovereign Boundaries (PSL-INV-008)
1. **Automated Architectural Fitness Gates**:
   - Production systems must satisfy automated architectural fitness checks evaluating layer boundaries, import acyclicity, and structural complexity.
2. **Strict Layer Boundaries & Public IP Hygiene**:
   - Enforce strict separation between distributable core libraries and workspace pipelines or scratchpads, keeping proprietary IP, personal paths, and secrets out of distributable/public artifacts.
3. **Externalized Assets & Bounded State**:
   - Decouple non-native language assets (HTML, CSS, JS, SQL) into `assets/` loaded via `importlib.resources` rather than embedding large multiline string monoliths in core code; enforce explicit capacity bounds (max items, LRU, or TTL) on all in-memory caches and lists.
4. **Acyclic Import Graph (DAG)**:
   - Maintain a strictly acyclic import graph across modules and packages via dependency inversion or interface segregation.

---

> **On-Demand Domain Pack — Cleanroom RE & Pre-Analyzed Ghidra Cache (`PSL-RE-001`)**: For binary reverse engineering, disassembly/decompilation, or cleanroom reconstruction, load `re-ops` (`harness/skills/re-ops/SKILL.md`) for `.dirtyroom/` isolation, `rea@6.9.0` obligation ledgers, and `-noanalysis -readOnly` Ghidra cache rules.
