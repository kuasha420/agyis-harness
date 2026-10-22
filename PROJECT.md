<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Project: Route C Swarm Hardening (Issue #83 Act 4)

## Architecture
- **Hook Lifecycle**: Google Antigravity `PreInvocation` lifecycle hook invoked prior to every model turn.
- **Ingress**: Receives JSON on `stdin` containing conversation context (`conversationId`, `workspacePaths`, `activeWorkspaces`, `tokens`, `token_count`, `role`).
- **Runner & CLI**: `harness/cli.py` exposes `agyis hook <hook_name>`, dispatching to `harness/hooks/runner.py`. The runner resolves canonical aliases, invokes the target hook module, and enforces fail-open guarantees (`{"injectSteps": []}` with exit code 0).
- **Advisory Engine**: `harness/hooks/pre_invocation_hook.py` evaluates token counts via direct payload inspection or read-only SQLite conversation database queries (`token_proximity_guard.py`). When tokens >= 230,000, classifies agent role and constructs ephemeral advisory with dynamic remaining turns runway.
- **Egress**: Returns protojson `{"injectSteps": []}` (below threshold or fail-open) or `{"injectSteps": [{"ephemeralMessage": advisory}]}` (at/above threshold).

## Feature Inventory
Every feature from the Survey phase is mapped to an assigned milestone:
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | F1: Runner Aliases | Register `"compaction-advisory"`, `"compaction_advisory"`, `"compaction"`, `"advisory"` in `runner.py:ALIASES` | M1 | COMPLETION_LEDGER.md §5 M1 |
| 2 | F2: Runner Fail-Open Normalization | Update `is_pre_invocation_context()` to recognize `"compaction"` and `"advisory"`, guaranteeing `{"injectSteps": []}` on failure | M1 | COMPLETION_LEDGER.md §5 M1 |
| 3 | F3: CLI Whitelist Registration | Add `"compaction-advisory"`, `"compaction_advisory"`, `"compaction"` to `harness/cli.py` argument choices | M1 | COMPLETION_LEDGER.md §5 M1 |
| 4 | F4: Ingress Key Alignment | Support both `"activeWorkspaces"` and official camelCase `"workspacePaths"` in `classify_agent_role()` | M2 | COMPLETION_LEDGER.md §5 M2 |
| 5 | F5: Custodian Role Mapping | Map `"custodian"` to `ROLE_DEEP_EXECUTION` in `_normalize_role_str()` for SWE ladder worktree safety | M2 | COMPLETION_LEDGER.md §5 M2 |
| 6 | F6: Modern Protobuf Blob SQLite Inspection | Enhance Heuristic 4 to inspect `metadata` and `step_payload` binary blobs alongside legacy `step_data` | M2 | COMPLETION_LEDGER.md §5 M2 |
| 7 | F7: Codified Fleet Calibration Metadata | Define and export `CALIBRATION_METADATA` in `harness/hooks/pre_invocation_hook.py` (230k threshold, 15.9k runway, 3-6 turns) | M3 | COMPLETION_LEDGER.md §5 M3 |
| 8 | F8: Dynamic Runway & Turns Calculation | Compute dynamic remaining turns (`(246_000 - tokens) // 3500`) and embed in advisory header in `build_compaction_advisory()` | M3 | COMPLETION_LEDGER.md §5 M3 |
| 9 | F9: Expanded Unit & Integration Tests | Author 8 new targeted tests in `tests/test_compaction_advisory.py` covering M1–M3 and post-compaction silence | M4 | COMPLETION_LEDGER.md §5 M4 |
| 10 | F10: Final E2E Pass & Adversarial Hardening | Pass 100% of E2E tests, verify ADR-015 sub-second benchmark (<1.0s), and verify clean project test suite exit code 0 | M5 | Issue #83 AC9 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Runner Alias & Fail-Open Normalization | `harness/hooks/runner.py`, `harness/cli.py` (F1, F2, F3) | none | DONE |
| M2 | Ingress Key Alignment & Custodian Role Mapping | `harness/hooks/pre_invocation_hook.py` (F4, F5, F6) | none | DONE |
| M3 | Codified Calibration Metadata & Dynamic Runway | `harness/hooks/pre_invocation_hook.py` (F7, F8) | M2 | DONE |
| M4 | Test Suite Expansion & Adversarial Verification | `tests/test_compaction_advisory.py` (F9) | M1, M2, M3 | DONE |
| M5 | Final Milestone: 100% E2E Pass & Hardening | Full test suite verification & adversarial challenge (F10) | M1, M2, M3, M4 | PARKED (QUIESCENT) |

## Interface Contracts
### CLI ↔ Runner
- `python3 -m harness.cli hook <hook_name>` accepts `"compaction-advisory"`, `"compaction_advisory"`, `"compaction"` and invokes `harness.hooks.runner.run_hook(<hook_name>, ...)`.

### Runner ↔ PreInvocation Hook
- Ingress: `stdin` json with `{"conversationId": "...", "tokenCount": ...}`.
- Fail-Open Contract: Any exception under `pre-invocation`, `compaction-advisory`, or related aliases emits:
  `{"injectSteps": []}` with exit code `0`.

### PreInvocation Hook ↔ Antigravity Platform
- Below threshold (< 230,000 tokens): `{"injectSteps": []}`.
- At/above threshold (>= 230,000 tokens):
  `{"injectSteps": [{"ephemeralMessage": "[AGYIS SYSTEM DIRECTIVE: COMPACTION IMMINENT (~{tokens:,} / 230,000 TOKENS | ~{estimated_turns} TURNS REMAINING)]\n..."}]}`.

## Code Layout
- Product Code:
  - `harness/hooks/runner.py` (Exclusive write ownership: Milestone 1 Worker)
  - `harness/cli.py` (Exclusive write ownership: Milestone 1 Worker)
  - `harness/hooks/pre_invocation_hook.py` (Exclusive write ownership: Milestone 2 & Milestone 3 Workers)
- Test Code:
  - `tests/test_compaction_advisory.py` (Exclusive write ownership: Milestone 4 Worker)
- Agent Metadata:
  - `.agents/teamwork/**` (Orchestrator, Workers, Reviewers, Challengers, Auditors metadata only)
