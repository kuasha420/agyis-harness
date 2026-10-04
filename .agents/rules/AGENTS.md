# Empirical Agent Rules: PSL Harness Guidelines

These operational rules govern cognitive behavior and human-in-the-loop alignment for **psl-agy-harness**. All deterministic environment guarantees (CPython >= 3.12 runtime injection, pager normalization, surgical grep exit sanitization, output compaction) are enforced transparently by harness hooks.

---

## 1. Explicit Project Command Dictionary (The Victory Pattern)
*Derived from purrmission & sunshine-physio: explicit CLI palettes yield 10x lower human intervention rates:*

```bash
# 🧪 Verification & Testing (Hermetic, <1.0s benchmark)
python3 -m harness.cli test                    # Run complete project test suite
python3 -m unittest discover -s tests -v        # Standard unittest runner

# 🩺 Environment Diagnostics & Auto-Healing
python3 -m harness.cli doctor                  # Audit 3-tier runtime matrix
python3 -m harness.cli doctor --heal           # Safe zero-sudo user-space repair
python3 -m harness.cli status                  # Print harness health, active hooks & telemetry

# 🪝 Lifecycle Hooks Dispatcher
python3 -m harness.cli hook command-safety     # PreToolUse terminal safety guard
python3 -m harness.cli hook anti-loop          # PreToolUse redundant call breaker
python3 -m harness.cli hook compactor          # PostToolUse 2KB output compactor

# 📊 Empirical Telemetry Laboratory
./psl sync                                     # Audit & synchronize active session into telemetry.db
./psl audit deep                               # Dissect 30 titan sessions (>=1k steps) & Knot inception
./psl audit volume                             # Analyze tool & command volume distributions
python3 -m harness.cli audit all               # Run full extraction, classification & summary
python3 -m harness.cli audit extract           # Ingest ~/.gemini/antigravity transcripts to telemetry.db
python3 -m harness.cli audit classify          # Categorize trajectories into WHAT_WORKED / WHAT_FAILED
python3 -m harness.cli audit inventory         # Catalog plugins, skills, hooks & MCP servers

# 🧩 Skills & Subagents Discovery
python3 -m harness.cli skills                  # List installed modular skills & triggers
python3 -m harness.cli agents                  # List registered specialist subagents & tools

# 🌐 Remote Operations & Cloud/Mesh Triage (ADR-027)
python3 -m harness.cli remote exec <target> "<cmd>"    # Multiplexed SSH with login-shell promotion
python3 -m harness.cli remote script <target> <file>   # Stdin script streaming (zero disk footprint)
python3 -m harness.cli remote script <target> <file> --stage # Staged execution with trap cleanup
python3 -m harness.cli remote triage <target>          # Compact (<2KB) multi-component health report
python3 -m harness.cli remote socket status            # List active OpenSSH ControlMaster sockets
python3 -m harness.cli remote socket cleanup           # Remove active ControlMaster sockets
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
   - The complete test suite must execute in **<1.0 second**. Slow operations, long sleeps, or disk sweeps are strictly prohibited in unit and integration test paths.
3. **Hermetic Isolation**:
   - Tests must never access the network or depend on external daemon services.
   - All state-persisting components must support `PSL_HARNESS_STATE_DIR` and use `tempfile.TemporaryDirectory()`.

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
   - Never poll `manage_task(Action='status')` in a loop; await reactive wakeups.
3. **Subagent Delegation Protocol**:
   - For multi-phase refactoring, test debugging, or massive build sweeps, delegate to subagents in isolated worktrees (`Workspace: "share"` or `"branch"`).

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
