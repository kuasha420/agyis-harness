# Empirical Agent Rules: PSL Harness Guidelines

These operational rules are grounded directly in the empirical audit of 348 developer sessions, 139,953 steps, and 2,229 tool failures recorded on this workstation (see `docs/taxonomy/workstation-audit-report.md`).

---

## 1. Terminal & Command Invariants (`run_command`)
*Terminal commands accounted for 98.4% of all tool failures (2,192 errors). Adhere strictly to the following:*

1. **Pre-flight Tool Availability (Mitigate Exit Code 127)**:
   - Never assume optional binaries exist. Before invoking a tool, verify availability (e.g. `which <bin>` or `command -v <bin>`) or handle fallback paths gracefully.
2. **Defend Against False-Failure Exit Codes (Mitigate Exit Code 1)**:
   - Benign commands like `grep`, `diff`, or `git diff | grep` exit with code `1` when no match is found. Do not treat empty search results as execution failures.
   - When running pattern matching commands where zero matches are acceptable, append `|| true` or test explicitly.
3. **Prevent Interactive TUI & Subshell Hangs**:
   - Commands must run strictly non-interactively. Never run commands that prompt for stdin without input redirection or piping.
   - Always run with `PAGER=cat` or disable pagers (`--no-pager`).
4. **Context Flood Prevention (The 200+ Step Context Cliff)**:
   - Never execute unfiltered commands that dump thousands of lines of output into context.
   - Pipe large outputs through `head -n <N>`, `tail -n <N>`, or `wc -l`.
   - Use targeted grep / ripgrep rather than recursive raw prints.
5. **Mesh & Hardware Remote Calls (Mitigate Exit Code 255)**:
   - SSH commands to Knot mesh nodes (`laptop`, `rog-ally`, `steamdeck`) must specify short connection timeouts (`-o ConnectTimeout=5`) and verify host reachability before running critical work.

---

## 2. Anti-Loop & Thrashing Heuristics
*Audit revealed 5,773 repeated consecutive tool calls (3,951 on `view_file`, 625 on `grep_search`, 300 on `manage_task`).*

1. **File Read State Retention**:
   - Do NOT repeatedly call `view_file` on the same file within consecutive steps unless an edit tool (`replace_file_content` or `write_to_file`) was executed in between.
   - Use the content already present in context rather than re-reading.
2. **Grep Query Evolution**:
   - If a `grep_search` returns zero results or fails, do NOT repeat the identical query. Broaden the pattern, check case-sensitivity, or inspect directory listing.
3. **No Polling Loops on Background Tasks**:
   - Never poll `manage_task(Action='status')` in a loop. Antigravity automatically wakes up the agent when a task finishes. Stop calling tools and await reactive wakeup.

---

## 3. Human-in-the-Loop & Steering Alignment
*Audit revealed 1,690 operator interventions, including 69 halt fences and frequent trajectory drift corrections.*

1. **Anti-Drift Commitment**:
   - Anchor all implementation decisions to the agreed plan. If novel obstacles arise requiring architectural deviation, pause and present options rather than silently pivoting.
2. **Proactive Confirmation Gates**:
   - When encountering destructive operations (file deletion, git branch force-push, remote node reboots), pause for explicit operator review.
3. **Clear Error Reporting**:
   - If a command fails twice, stop thrashing. State the error concisely, identify the underlying cause, and propose a concrete path forward.
