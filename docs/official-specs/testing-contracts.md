<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Official Specification: Testing Contracts & Verification Architecture

**Project**: Agyis Harness for Google Antigravity™ (`agyis-harness`)  
**Publisher**: Purrfect Software Limited (PSL)  
**License**: Apache-2.0  
**Scope**: Project-Internal Test Standards & Product-Delivered Testing Invariants  
**Last Updated**: 2026-11-11  

---

## 1. Executive Summary

Empirical telemetry across 722 sessions, 219,292 steps, and 160,226 tool calls demonstrated that **agent testing behavior is the single most decisive factor in determining whether an autonomous session succeeds or drifts**:

- Workspaces with explicit, deterministic testing contracts (e.g. `purrmission`, `sunshine-physio-universalapp`) achieved **1.67–1.91 operator interventions/session**.
- Workspaces with ambiguous, unconfigured, or implicit testing practices experienced **18.2–36.0 interventions/session** (a 10x–20x degradation).
- **The Premature Convergence Trap**: Models frequently declare tasks "complete" after writing code without running tests, or after inspecting a single unrelated command.

To eliminate this failure mode, this specification establishes two distinct tiers:
1. **Tier 1: Project-Internal Testing Contract**: How Agyis Harness itself is tested, verified, and benchmarked.
2. **Tier 2: Product-Delivered Testing Invariants**: How Agyis Harness will enforce verification contracts in client workspaces.

---

## 2. Tier 1: Project-Internal Testing Contract

All unit, integration, and replay tests within the `agyis-harness` repository (`tests/`) must strictly adhere to the following 5 invariants:

### A. The Hermetic Isolation Invariant
- Tests must **never** make network calls, spawn daemon services, or mutate host-global state.
- All state-persisting components (such as `anti_loop_hook` and `output_compactor_hook`) must accept configurable state directories via `state_dir: Optional[Path]` and environment variable overrides (`AGYIS_HARNESS_STATE_DIR` / `PSL_HARNESS_STATE_DIR`).
- Test fixtures must use `tempfile.TemporaryDirectory()` and clean up on teardown.

### B. The Sub-Second Benchmark Invariant
- Individual unit and contract test modules must execute in **less than 1.0 second** (sub-second component benchmark), while the complete suite (currently verified across **1,981 tests in ~65s**) runs hermetically with zero external dependencies.
- Slow operations (such as long sleeps, heavy model invocations, or disk-heavy sweeps) are strictly prohibited in unit and integration test paths.
- Micro-benchmark latency for individual hooks must remain under 1 ms (currently verified at <0.25 ms for the 2KB output compactor).

### C. The Official Platform Contract Invariant
Every lifecycle hook must be tested against the official Antigravity protojson stdin/stdout contract:
- **`PreToolUse`**: Validates input containing `conversationId`, `stepIdx`, `toolCall` (`name` and `args`), and asserts output schema (`decision`: `"allow"` or `"deny"`, optional `overwrite` and `reason`).
- **`PostToolUse`**: Validates input containing `toolOutput` / `content`, `exitCode`, and asserts output is exact JSON `{}` with exit code `0`.
- **Fault Tolerance**: Malformed JSON, non-dictionary payloads, or empty stdin must never crash the hook or block agent execution; they must gracefully fail open (`{"decision": "allow"}` or `{}`).

### D. The Telemetry Replay Invariant
- Defensive hooks must include replay test cases derived directly from historical failure trajectories in `data/telemetry.db`.
- Example: [test_command_safety.py](../../tests/test_command_safety.py) replays the exact PEP 701 f-string syntax crash from session `270b7abc` to verify that hermetic Python injection and f-string sanitization neutralize the bug.

### E. Test File Mapping & Suite Execution
The `tests/` directory houses **77** `tests/test_*.py` modules totaling **1,981** automated tests (representative core modules below):
```text
tests/
├── test_agent_scaffold.py           # 15 tests: agent scaffolding, workspace discovery, YAML frontmatter
├── test_anti_drift.py               # 40 tests: plan boundary enforcement, native plan-mode lock, exemptions
├── test_anti_loop.py                # 18 tests: repeat thresholds, reactive wait invariant, frequency window
├── test_cli.py                      # 27-command CLI dispatcher, command routing, lazy pipeline loading
├── test_command_safety.py           # 18 tests: dangerous patterns, TUI blocks, hermetic python, grep rewrite
├── test_command_safety_remote.py    # 9 tests: remote grep rewrite, ControlMaster multiplexing, SSH timeouts
├── test_completion_fence.py         # 22 tests: dirty code tracking, exemptions, anti-deadlock safety valve
├── test_conversation_harvester.py   # 10 tests: transcript ingestion, step extraction, token tracking
├── test_delivery.py                 # 18 tests: global plugin installer, 3-tier precedence, zero git pollution
├── test_display_bridge.py           # 4 tests: base64 image decoding, screen capture bridge, corrupt URI handling
├── test_failure_clusters.py         # 4 tests: cross-model failure mining, exit code clusters, intervention buckets
├── test_hook_runner.py              # 18 tests: fail-safe dispatcher, fail-open contracts, argument pass-through
├── test_output_compactor.py         # 19 tests: 2KB boundary, failure preservation, JSON contract, head/tail slicing
├── test_pipeline_audit_smoke.py     # 1 test: hermetic telemetry pipeline smoke test on temporary database
├── test_psl_doctor.py               # 24 tests: 3-tier matrix auditing, uv auto-healing, distro detection
├── test_redaction.py                # 25 tests: private key scrub, API tokens, path anonymization
├── test_remote_runner.py            # 14 tests: SSH runner, stdin script streaming, compact triage reports
├── test_server_api.py               # 8 tests: Starlette gateway endpoints, dual-engine storage, push/pull
├── test_skills.py                   # 12 tests: skill discovery, frontmatter parsing, mirror synchronization
├── test_subagent_context.py         # 11 tests: microsecond token estimation, health zones (healthy/amber/red)
├── test_subagents.py                # 19 tests: specialist archetypes, capability bundles, spec validator
├── test_telemetry_sync.py           # 47 tests: bi-directional sync, chunked push, anti-echo filter, ADR-014
├── test_ultra_deep_analyzer.py      # 6 tests: titan sessions analysis, survival archetypes
└── test_volume_mining.py            # 5 tests: tool character volume distributions, compaction simulations
```

Run test suite via:
```bash
agyis test
# or: python3 -m harness.cli test
# or standard unittest discover:
python3 -m unittest discover -s tests -v
```

---

## 3. Tier 2: Product-Delivered Testing Invariants (The Roadmap Blueprint)

As the harness transitions from Horizon 0 research into the Horizon 1 distributable product, Agyis Harness will deliver active testing intelligence to client workspaces through three mechanisms:

### A. The Harness Testing Rule (`rules/AGENTS.md`)
The harness injects the **Clean-Room Verification Invariant** into the agent's active cognitive rules:
1. **Mandatory Automated Verification**:
   - The agent is forbidden from declaring a task "done", "fixed", or "complete" without executing the project's canonical test suite and verifying exit code 0.
2. **Explicit Command Anchoring**:
   - The agent must check the project ledger or rules for the explicit test command rather than probing speculative commands (`npm test`, `pytest`, `cargo test`).
3. **Failure Isolation**:
   - When tests fail, the agent must isolate the failing assertion, avoid repeating the exact identical test command without code modifications (Anti-Loop Invariant), and present the failure reason concisely.

### B. The `Stop` Lifecycle Verification Fence (`completion_fence_hook.py` / `fence_gates.py`)
In Antigravity's lifecycle, the `Stop` event fires when the agent finishes its turn (`terminationReason: "model_stop"`):
- If the agent has modified source or spec files (`*.py`, `*.ts`, `*.go`, `*.rs`, or `docs/specs/**`) during the session, but **zero verification test commands** were executed, the `Stop` hook blocks stop (`"decision": "continue"`) and returns (inside the `agyis-harness` repository or consumer projects respectively):
  ```json
  {
    "decision": "continue",
    "reason": "Verification Required: Unverified code edits detected in: path/to/file.py. Execute 'agyis test' (or 'python3 -m harness.cli test') before stopping."
  }
  ```
- Note: For external consumer repositories, the reason reads `Execute your project test suite (<detected_runner>) before stopping.`, and for unverified `docs/specs/**` or `.agents/ledger/*.json` edits without code changes it returns `Cleanroom Verification Required: Unverified cleanroom contract edits detected in: <files>. Execute 'rea verify-reconstruction' or 'agyis verify --spec' before stopping.`.
- This deterministically prevents "Premature Convergence" where models hallucinate that their changes work without running verification.

### C. Standardized Test Runner Skills
Agyis Harness supplies modular on-demand testing skills (`psl-test-python`, `psl-test-node`, `psl-test-cargo`, `psl-test-go`, `psl-test-harmonize`) that:
- Enforce hermetic execution contracts and diff-aware targeted runs (`test:diff`, `test:affected`, `test:full`).
- Extract failing test cases, stack traces, and assertions cleanly.
- Work alongside `output_compactor` hooks to keep test output compact before the agent processes it.
