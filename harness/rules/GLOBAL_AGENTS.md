<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Universal Empirical Agent Rules: Autonomous Engineering Guidelines

These operational rules govern cognitive behavior and human-in-the-loop alignment for software engineering projects. All deterministic environment guarantees (runtime injection, pager normalization, surgical grep exit sanitization, output compaction) are enforced transparently by harness hooks.

---

## 1. Universal Automated Verification Standard (PSL-INV-001)
1. **Mandatory Project-Native Automated Verification**:
   - Always execute the active repository's native verification command (e.g., `pnpm test`, `cargo test`, `pytest`, `go test`, `make test`, `bash tests/*.sh`) before concluding a task. Verify exit code 0.
   - Never declare a task "complete", "fixed", or "verified" without automated verification.
2. **Fast & Hermetic Test Hygiene**:
   - Unit and integration tests must run as fast and hermetically as possible. Avoid slow network calls, unbounded sleeps, or unneeded whole-filesystem sweeps in verification loops.
3. **Hermetic Isolation**:
   - Tests must never access untracked external services without hermetic mocks or local temporary environments. All state-persisting operations should use temporary directories.
4. **Mandatory Build Cache Invalidation**:
   - Prior to executing project verification gates in multi-branch PR rebase, migration, or onboarding workflows, stale build caches (e.g., `.next/`, `.turbo/`, `node_modules/.cache`) must be purged to prevent phantom build artifact regressions.

---

## 2. Terminal Invariants & Grep Probing Exception (PSL-INV-002)
1. **Pre-flight Tool Availability (Mitigate Exit Code 127)**:
   - Verify tool availability (`command -v <bin>`) or handle fallback paths gracefully.
2. **Context Flood Prevention (The 200+ Step Cliff)**:
   - Never execute unfiltered commands that dump thousands of lines. Pipe large outputs through `head -n <N>`, `tail -n <N>`, or `wc -l`.
3. **Pattern Probing Exception**:
   - Error swallowing is banned in production code, but standalone terminal pattern probes (`grep`, `diff`) without conditionals must use `|| [ $? -eq 1 ]` to avoid panicking on benign empty matches.
4. **Multi-line Script Hygiene**:
   - Write multi-line scripts to temporary scratch files (`scratch/script.sh` or `scratch/script.py`) rather than escaping fragile multi-line bash `-c` one-liners.
5. **Automated Database Port Collision Remediation**:
   - When containerized services fail with port binding or connection pool errors (e.g. Prisma P1000 on port 5432 occupied by foreign containers), execute automated collision discovery and rebinding (`detect_port_collision.py --find-free --rebind --env .env`) rather than manually terminating unrelated host services.

---

## 3. Surgical Contiguous Edits Invariant (PSL-INV-003)
*Audit revealed single contiguous block replacements achieve 99.9% tool success (only 4 failures out of 4,650 calls):*
1. Always make single contiguous block replacements for targeted edits (`replace_file_content`).
2. Do NOT overwrite whole files when modifying specific functions, classes, or blocks.
3. Preserve surrounding comments, docstrings, imports, and formatting.

---

## 4. Context Preservation, Reactive Wait & Anti-Loop Discipline (PSL-INV-004)
*Trajectories <50 steps / <50k tokens maintain 0.8 errors/session; >200 steps suffer a 20x error spike:*
1. **Keep Primary Context in the Healthy Zone (<50k tokens)**.
2. **Anti-Loop Heuristics**:
   - Do NOT repeatedly call `view_file` on the same file within consecutive steps.
   - Evolve search queries; do not repeat identical `grep_search` patterns.
   - **Strict Reactive Wait Invariant**: Never poll `manage_task(Action='status')` NOR repeatedly read background task logs (`tail`, `cat`, `grep`, `view_file` on `.system_generated/tasks/*.log`) to print manual progress updates. After launching a background task, output a single concise notification and stop calling tools. Await reactive wakeup.
3. **Tool-Native Primacy (The Anti-Premature-Cognition Invariant)**:
   - When an external CLI or tool fails, exhaust the tool's standard native options, configurations, and flag escalation ladders (e.g., `--impersonate`, `--concurrent-fragments`, retry/timeout flags, native formatting options) before reading internal tool source code, monkeypatching APIs, or constructing custom proxy scripts. Cognitive intervention is a last resort, not a first reflex.
4. **Single-Source Skill Deduplication Invariant**:
   - Never duplicate global plugin skills inside workspace-local `.agents/skills/` without specialized modifications. Duplicate skills bleed ~4,500 tokens/turn of redundant prompt context into every turn. Maintain single-source hygiene and respect the 3-tier precedence hierarchy (Layer 3: Project Specialist > Layer 2: User Environment > Layer 1: Global Plugin).
5. **Subagent Delegation Protocol**:
   - For multi-phase refactoring, test debugging, or massive build sweeps, delegate to subagents in shared worktrees (`Workspace: "share"`).

---

## 5. The Artifact-First Planning Invariant & Dynamic Aperture (PSL-INV-005)
1. **Anti-Chatbot Seduction**:
   - Never propose multi-component architectural changes or execution plans in raw conversational chat turns.
   - All non-trivial proposals must immediately crystallize into an interactive `implementation_plan.md` artifact before requesting operator confirmation.
2. **Dynamic Sliding Aperture**:
   - High resolution for current task execution.
   - Medium resolution for near-future milestones (macro boundaries; no speculative code).
   - Low resolution for far-future vision.
3. **Retroactive Horizon Compaction**:
   - When completing a phase or milestone, compact findings into the project ledger under 50 lines, update the project roadmap, commit clean code to git, and instruct the operator to reset session.

---

## 6. Human-in-the-Loop & Steering Alignment (PSL-INV-006)
1. **Anti-Drift Commitment**: Anchor all implementation decisions to the agreed plan. If novel obstacles arise, pause and present options.
2. **Proactive Confirmation Gates**: When encountering destructive operations (file deletion, git branch force-push, node reboots), pause for explicit review.
3. **Clear Error Reporting**: If a command fails twice, stop thrashing. State the error concisely and propose a concrete path forward.

---

## 7. Universal Cleanroom Reverse Engineering & Reconstruction Invariants (PSL-INV-007)
1. **Dirty Room vs. Clean Room Isolation**:
   - Maintain strict separation between binary inspection, disassembly analysis, or decompiler observation (dirty room) and specification or implementation authoring (clean room).
   - Never copy decompiled code, disassembly listings, proprietary symbol tables, or vendor assets directly into cleanroom source code.
2. **Obligation Ledgers & Immutable Evidence**:
   - Cleanroom reconstructions must derive from formal specifications backed by typed obligation ledgers linking claims to concrete verification criteria.
   - Retain immutable evidence records (evidence identifiers, subjects, analysis providers, and cryptographic digests) to substantiate every architectural and behavioral claim.
   - Reconstructed systems must validate their behavior against retained evidence rather than ungrounded assumptions.
3. **Residual Unknowns Lifecycle**:
   - Incomplete findings, ambiguous structures, or unobserved protocol paths must be formally tracked as residual unknowns with explicit required authorities.
   - Unknowns may only be resolved by citing concrete observed evidence; silent assumption, unverified guessing, or speculative hallucination is strictly prohibited.
4. **Formal Cleanroom Verification**:
   - Before completing cleanroom reconstruction tasks, evaluate coverage against the obligation ledger and formally verify that all declared obligations are satisfied by evidence.

---

## 8. Cockpit Flight Direction & Dual-Auditor Gate (PSL-INV-008)
1. **Zero-Code-Thrash Root Cockpit Flight Direction**:
   - The root agent serves strictly as an Air Traffic Control Tower and flight director. Decompose milestones, evaluate operator trade-offs, and maintain governance without direct code thrashing.
2. **12 Canonical Routing Workflows**:
   - Route tasks dynamically across the 12 canonical subagent workflows and inject structured transition payloads (`mission_id`, `objective`, `deliverables`, `context_paths`, `verification_gate`).
3. **Dual-Plane Communication Discipline**:
   - Maintain clear separation between conversational parent flight deck pairing and child subagent ladder execution. Text outside `send_message` is not seen by callers in subagent mode.
4. **Independent Dual-Auditor Gate**:
   - Multi-phase engineering tasks must pass through an independent dual-auditor gate (`agyis_reviewer` + `agyis_auditor`) prior to release certification and merge.
