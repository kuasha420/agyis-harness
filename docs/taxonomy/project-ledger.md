# 📜 PSL Harness Project Ledger (Compacted Horizon 0)

This ledger preserves permanent architectural decisions, schema contracts, and verified baseline metrics across completed phases. Detailed operational logs fade into git history and archives.

---

## [Phase 1] Foundation, Baseline Telemetry & Ecosystem Audit
* **Status**: Completed | **Compaction Date**: 2026-10-02
* **Key Architectural Decisions (ADRs)**:
  - **ADR-001 (License & Stance)**: Apache-2.0 open-source initiative. Build on and extend official Google Antigravity surfaces (`plugin.json`, hooks, rules) rather than building an isolated competing framework.
  - **ADR-002 (Telemetry Schema)**: Structured SQLite database (`data/telemetry.db`) mapping sessions, steps, tool calls, and human interventions.
  - **ADR-003 (Dynamic Aperture Planning)**: Adopted Resolution Gradient with Retroactive Horizon Compaction—high-res present, mid/low-res future, and compacted permanent ledger past.
* **Empirical Baselines Established**:
  - **Volume**: 348 sessions, 140,005 steps, 64,065 tool calls, 2,232 tool failures, 1,690 operator interventions.
  - **Root Cause**: `run_command` accounts for 98.4% of all tool failures (1,541 Exit Code 1, 143 Exit Code 127).
  - **Loop Traps**: 5,773 repeated consecutive calls (3,951 `view_file`, 625 `grep_search`, 300 `manage_task`).
  - **Context Cliff**: Trajectories >200 steps suffer a 20x error spike (1.0 -> 20.5) and 40x intervention spike (0.4 -> 16.3).
  - **Rule Calibration**: Explicit command dictionaries (e.g. `purrmission`) yield 1.67 interventions/session; multi-file rule indirection (e.g. `mm-website`) causes 18.2 interventions/session (10x higher).
* **Reference Harness Assets Committed**:
  - Manifest: [plugin.json](file:///home/kuasha/Dev/psl-agy-harness/plugin.json)
  - Rules: [.agents/rules/AGENTS.md](file:///home/kuasha/Dev/psl-agy-harness/.agents/rules/AGENTS.md)
  - Lifecycle Hooks: [harness/hooks/anti_loop_hook.py](file:///home/kuasha/Dev/psl-agy-harness/harness/hooks/anti_loop_hook.py), [harness/hooks/command_safety_hook.py](file:///home/kuasha/Dev/psl-agy-harness/harness/hooks/command_safety_hook.py), [harness/hooks/hooks.json](file:///home/kuasha/Dev/psl-agy-harness/harness/hooks/hooks.json).
  - Skill: [.agents/skills/psl-audit-toolkit/SKILL.md](file:///home/kuasha/Dev/psl-agy-harness/.agents/skills/psl-audit-toolkit/SKILL.md)
