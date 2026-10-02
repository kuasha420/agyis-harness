# Empirical Agent Rules: PSL Harness Guidelines

These operational rules govern cognitive behavior and human-in-the-loop alignment. All deterministic environment guarantees (CPython >= 3.12 runtime injection, pager normalization, surgical grep exit sanitization, output compaction) are enforced transparently by harness hooks and require zero prompt overhead.

---

## 1. Terminal Invariants & Context Protection
*Terminal commands accounted for 98.4% of all tool failures in telemetry:*

1. **Pre-flight Tool Availability (Mitigate Exit Code 127)**:
   - Never assume optional binaries exist. Verify availability (`command -v <bin>`) or handle fallback paths gracefully.
2. **Context Flood Prevention (The 200+ Step Cliff)**:
   - Never execute unfiltered commands that dump thousands of lines into context. Pipe large outputs through `head -n <N>`, `tail -n <N>`, or `wc -l`.
3. **Multi-line Script Hygiene**:
   - For Python scripts longer than a single expression, write to `<artifactDir>/scratch/script.py` and execute the file rather than wrestling with double-escaped bash `-c` strings.
4. **Mesh Remote Calls (Mitigate Exit Code 255)**:
   - SSH commands to Knot mesh nodes (`laptop`, `rog-ally`, `steamdeck`) must specify connection timeouts (`-o ConnectTimeout=5`) and verify host reachability.

---

## 2. Anti-Loop & Thrashing Heuristics
*Audit revealed 5,773 repeated consecutive tool calls:*

1. **File Read State Retention**:
   - Do NOT repeatedly call `view_file` on the same file within consecutive steps unless an edit tool was executed in between. Use content already present in context.
2. **Grep Query Evolution**:
   - If a `grep_search` returns zero results, do NOT repeat the identical query. Broaden the pattern, check case-sensitivity, or inspect directory listing.
3. **Reactive Task Wakeups**:
   - Never poll `manage_task(Action='status')` in a loop. Antigravity automatically wakes up the agent when a task finishes. Stop calling tools and await reactive wakeup.

---

## 3. Human-in-the-Loop & Steering Alignment
*Audit revealed 1,690 operator interventions and 69 halt fences:*

1. **Anti-Drift Commitment**:
   - Anchor all implementation decisions to the agreed plan. If novel obstacles arise requiring architectural deviation, pause and present options rather than silently pivoting.
2. **Proactive Confirmation Gates**:
   - When encountering destructive operations (file deletion, git branch force-push, remote node reboots), pause for explicit operator review.
3. **Clear Error Reporting**:
   - If a command fails twice, stop thrashing. State the error concisely, identify the underlying cause, and propose a concrete path forward.

---

## 4. The Resolution Gradient & Horizon Compaction Invariant
1. **Dynamic Sliding Aperture**:
   - Keep current task execution at **High Resolution** (concrete file edits, explicit tests, verifiable exit codes).
   - Near-future items remain at **Medium Resolution** (macro milestones and architectural boundaries; do not write speculative code or micro-specs).
   - Far-future items remain at **Low Resolution** (strategic vision in documentation).
2. **Retroactive Horizon Compaction**:
   - When completing a phase or milestone, implementation details, scratch scripts, and multi-turn debug transcripts fade out into git history.
   - Only permanent Architectural Decisions (ADRs), schema contracts, and verified baseline metrics are retained in the project ledger (`docs/taxonomy/project-ledger.md`), strictly constrained under 50 lines per milestone.

---

## 5. The Artifact-First Planning Invariant (ADR-012)
1. **Anti-Chatbot Seduction**:
   - Never propose multi-component architectural changes or multi-step execution plans in raw conversational chat turns.
   - All non-trivial proposals must immediately crystallize into an interactive `implementation_plan.md` artifact before requesting operator confirmation.
   - Never end turns with open-ended conversational proposals (*"Would you like me to build X?"*) without an accompanying plan artifact.
