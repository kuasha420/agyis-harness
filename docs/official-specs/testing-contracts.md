# Official Specification: Testing Contracts & Verification Architecture

**Project**: PSL Harness for Google Antigravity™ (`psl-agy-harness`)  
**Publisher**: Purrfect Software Limited (PSL)  
**License**: Apache-2.0  
**Scope**: Project-Internal Test Standards & Product-Delivered Testing Invariants  
**Last Updated**: 2026-10-02  

---

## 1. Executive Summary

Empirical telemetry across 348 sessions and 140,005 steps demonstrated that **agent testing behavior is the single most decisive factor in determining whether an autonomous session succeeds or drifts**:

- Workspaces with explicit, deterministic testing contracts (e.g. `purrmission`, `sunshine-physio-universalapp`) achieved **1.67–1.91 operator interventions/session**.
- Workspaces with ambiguous, unconfigured, or implicit testing practices experienced **18.2–36.0 interventions/session** (a 10x–20x degradation).
- **The Premature Convergence Trap**: Models frequently declare tasks "complete" after writing code without running tests, or after inspecting a single unrelated command.

To eliminate this failure mode, this specification establishes two distinct tiers:
1. **Tier 1: Project-Internal Testing Contract**: How PAH itself is tested, verified, and benchmarked.
2. **Tier 2: Product-Delivered Testing Invariants**: How PAH will enforce verification contracts in client workspaces.

---

## 2. Tier 1: Project-Internal Testing Contract

All unit, integration, and replay tests within the `psl-agy-harness` repository (`tests/`) must strictly adhere to the following 5 invariants:

### A. The Hermetic Isolation Invariant
- Tests must **never** make network calls, spawn daemon services, or mutate host-global state.
- All state-persisting components (such as `anti_loop_hook` and `output_compactor_hook`) must accept configurable state directories via `state_dir: Optional[Path]` and environment variable overrides (`PSL_HARNESS_STATE_DIR`).
- Test fixtures must use `tempfile.TemporaryDirectory()` and clean up on teardown.

### B. The Sub-Second Benchmark Invariant
- The entire test suite must execute in **less than 1.0 second**.
- Slow operations (such as long sleeps, heavy model invocations, or disk-heavy sweeps) are strictly prohibited in unit and integration test paths.
- Micro-benchmark latency for individual hooks must remain under 1 ms (currently verified at <0.25 ms for the 2KB output compactor).

### C. The Official Platform Contract Invariant
Every lifecycle hook must be tested against the official Antigravity protojson stdin/stdout contract:
- **`PreToolUse`**: Validates input containing `conversationId`, `stepIdx`, `toolCall` (`name` and `args`), and asserts output schema (`decision`: `"allow"` or `"deny"`, optional `overwrite` and `reason`).
- **`PostToolUse`**: Validates input containing `toolOutput` / `content`, `exitCode`, and asserts output is exact JSON `{}` with exit code `0`.
- **Fault Tolerance**: Malformed JSON, non-dictionary payloads, or empty stdin must never crash the hook or block agent execution; they must gracefully fail open (`{"decision": "allow"}` or `{}`).

### D. The Telemetry Replay Invariant
- Defensive hooks must include replay test cases derived directly from historical failure trajectories in `data/telemetry.db`.
- Example: [test_command_safety.py](file:///home/kuasha/Dev/psl-agy-harness/tests/test_command_safety.py) replays the exact PEP 701 f-string syntax crash from session `270b7abc` to verify that hermetic Python injection and f-string sanitization neutralize the bug.

### E. Test File Mapping & Suite Execution
```text
tests/
├── test_anti_loop.py        # 7 tests: repeat thresholds, mutation resets, conversation isolation
├── test_command_safety.py   # 8 tests: dangerous patterns, TUI block, hermetic python, grep rewrite
├── test_output_compactor.py # 13 tests: 2KB boundary, failure preservation, JSON contract, transcript fallback
└── test_psl_doctor.py       # 8 tests: version parsing, matrix auditing, distro detection
```

Run test suite via:
```bash
python3 -m unittest discover -s tests -v
```

---

## 3. Tier 2: Product-Delivered Testing Invariants (The Roadmap Blueprint)

As the harness transitions from Horizon 0 research into the Horizon 1 distributable product, PAH will deliver active testing intelligence to client workspaces through three mechanisms:

### A. The Harness Testing Rule (`rules/AGENTS.md`)
The harness injects the **Clean-Room Verification Invariant** into the agent's active cognitive rules:
1. **Mandatory Automated Verification**:
   - The agent is forbidden from declaring a task "done", "fixed", or "complete" without executing the project's canonical test suite and verifying exit code 0.
2. **Explicit Command Anchoring**:
   - The agent must check the project ledger or rules for the explicit test command rather than probing speculative commands (`npm test`, `pytest`, `cargo test`).
3. **Failure Isolation**:
   - When tests fail, the agent must isolate the failing assertion, avoid repeating the exact identical test command without code modifications (Anti-Loop Invariant), and present the failure reason concisely.

### B. The `Stop` Lifecycle Verification Fence (`completion_fence_hook.py`)
In Antigravity's lifecycle, the `Stop` event fires when the agent finishes its turn (`terminationReason: "model_stop"`):
- If the agent has modified source files (`*.py`, `*.ts`, `*.go`, `*.rs`) during the session, but **zero verification test commands** were executed, the `Stop` hook returns:
  ```json
  {
    "decision": "continue",
    "reason": "PSL Verification Fence: Source files were modified, but automated tests have not been executed. Run the project verification suite before completing."
  }
  ```
- This deterministically prevents "Premature Convergence" where models hallucinate that their changes work without running verification.

### C. Standardized Test Runner Skills
PAH will supply on-demand testing skills (`psl-test-runner`) that:
- Automatically parse output from standard test runners (pytest, vitest, cargo test, go test).
- Extract only failing test cases, stack traces, and assertions.
- Compact test outputs to prevent context flooding before the agent processes them.
