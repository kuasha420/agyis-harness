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

Empirical telemetry in [`../taxonomy/empirical-baselines.md`](../taxonomy/empirical-baselines.md) (`1,734` classified sessions / `2,875` live sessions) demonstrates that **explicit verification contracts decide whether autonomous sessions stay anchored or require operator rescues**:

- Workspaces with explicit, deterministic testing commands and gates (e.g., `<client-repo-ts>`, `<client-repo-rn>`) achieved **1.67–1.91 operator interventions/session**.
- Workspaces with ambiguous or implicit verification rules suffered **18.2–36.0 interventions/session** (a 10x–20x degradation).
- **The Premature Convergence Trap**: Models frequently declare tasks complete after editing code or running an unrelated probe without executing the repository's native verification gate.

This specification defines two canonical verification contracts:
1. **Tier 1: Project-Internal Testing Contract**: How `agyis-harness` itself (`tests/`) is isolated, structured, and verified.
2. **Tier 2: Product-Delivered Testing Invariants**: How `agyis-harness` enforces deterministic verification gates across managed workspaces.

---

## 2. Tier 1: Project-Internal Testing Contract

All unit, integration, and replay tests inside `tests/` must adhere to five invariants:

### A. The Hermetic Isolation Invariant
- Tests must **never** perform live network calls, depend on background daemons, or mutate host-global directories (`~/.gemini/`, `/tmp/agyis_harness_state_{uid}` outside isolated fixture dirs).
- All state-persisting components (`anti_loop_hook`, `output_compactor_hook`, `completion_fence_hook`, `token_proximity_guard`) resolve their default runtime directory at `/tmp/agyis_harness_state_{uid}` via `harness/utils/state.py` and support `state_dir: Optional[Path]` plus `AGYIS_HARNESS_STATE_DIR` / `PSL_HARNESS_STATE_DIR` environment overrides.
- Fixtures must allocate isolated temporary directories (`tempfile.TemporaryDirectory()`) and clean up on teardown.

### B. The Sub-Second Benchmark Invariant
- Individual component test modules must execute cleanly in **under 1.0 second**, while the macro repository suite across all **77** `tests/test_*.py` modules executes hermetically (`./agyis test` or `python3 -m harness.cli test`) with zero external service dependencies.
- Unbounded sleeps, slow model invocations, and whole-filesystem sweeps are strictly prohibited in unit and integration tests.
- Hook dispatch overhead remains sub-millisecond in steady state (verified at `<0.25 ms` / `241.3 us` on `50 KB` payloads for the 2 KB output compactor).

### C. The Official Platform Contract Invariant
Every lifecycle hook must be validated against Antigravity's camelCase protojson stdio contract ([`lifecycle-hooks.md`](lifecycle-hooks.md)):
- **`PreToolUse`**: Accepts `conversationId`, `stepIdx`, `toolCall` (`name`, `args`) and emits valid decision JSON (`"allow"`, `"deny"`, `"ask"`, `"force_ask"`), optional shallow `overwrite`, and `reason`.
- **`PostToolUse`**: Validates tool completion / `error` payloads and strictly emits `{}` with exit code `0`.
- **`PreInvocation` / `Stop`**: Emits valid `injectSteps` (with nested `systemMessage` envelopes) or `Stop` gating JSON (`decision: "continue"` vs allow), and all hooks fail open on malformed JSON or empty stdin.

### D. The Telemetry Replay Invariant
- Defensive hooks include regression replay cases derived from historical failure trajectories recorded in `data/telemetry.db` (e.g., [test_command_safety.py](../../tests/test_command_safety.py) replays the PEP 701 f-string syntax trap to guarantee CPython >= 3.12 sanitization).

### E. Suite Layout & Execution Commands
The `tests/` tree comprises **77** `tests/test_*.py` hermetic modules covering hooks, CLI commands, subagent contracts, delivery, cleanroom verification, and empirical pipeline stages (representative suites):
```text
tests/
├── test_agent_scaffold.py           # Agent scaffolding, workspace discovery, YAML frontmatter
├── test_anti_drift.py               # Plan boundary enforcement, native plan-mode lock, exemptions
├── test_anti_loop.py                # Repeat thresholds, reactive wait invariant, Issue #41 manage_task advisory
├── test_cli.py                      # 28-command CLI dispatcher, subparser routing, lazy pipeline loading
├── test_command_safety.py           # Dangerous patterns, TUI blocks, hermetic CPython, grep rewrite
├── test_command_safety_remote.py    # Remote grep rewrite, ControlMaster multiplexing, SSH timeouts
├── test_completion_fence.py         # Decoupled code_dirty/spec_dirty gating, exemptions, 2-block safety valve
├── test_conversation_harvester.py   # Transcript ingestion, protobuf step extraction, token tracking
├── test_delivery.py                 # Global plugin installer, 3-tier precedence, zero git pollution
├── test_hook_runner.py              # Fail-safe dispatcher, fail-open contracts, argument pass-through
├── test_output_compactor.py         # 2KB boundary, failure preservation, JSON contract, head/tail slicing
├── test_pipeline_audit_smoke.py     # Hermetic telemetry pipeline smoke test on temporary database
├── test_psl_doctor.py               # 3-tier matrix auditing, uv auto-healing, distro detection
├── test_redaction.py                # Private key scrub, API tokens, path anonymization
├── test_remote_runner.py            # SSH runner, stdin script streaming, compact triage reports
├── test_skills.py                   # Skill discovery, <24,576 B cap, >100 L ToC, dynamic REA provisioning
├── test_subagent_context.py         # Microsecond token estimation, health zones (healthy/amber/red)
├── test_subagents.py                # Specialist archetypes, 7 capability bundles, 17-tool validator
├── test_telemetry_sync.py           # Bi-directional sync, chunked push, anti-echo filter, ADR-014
├── test_verify.py                   # Cleanroom spec check & obligation_ledger.json schema verification
└── test_volume_mining.py            # Tool character volume distributions, compaction simulations
```

Run the project verification gates via:
```bash
agyis test
# or: python3 -m harness.cli test
# or standard unittest discover:
python3 -m unittest discover -s tests -v
```

---

## 3. Tier 2: Product-Delivered Testing Invariants

`agyis-harness` enforces deterministic verification across onboarded consumer workspaces through three coordinated layers:

### A. The Harness Testing Rule (`rules/AGENTS.md`)
Workspace rules codify the **Clean-Room Verification Invariant**:
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
