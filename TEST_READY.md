# TEST_READY.md — Agyis Harness v1.0.0 E2E Bug Bash Test Suite

## Status: READY & VERIFIED (100% Green)

The comprehensive opaque-box E2E test suite for **Agyis Harness v1.0.0 Full-Surface Bug Bash** (covering Quadrant 1: Real-Project Onboarding & Harmonization, and Quadrant 4: Live In-Situ HUD Dogfooding) has been fully authored, verified, and stabilized.

---

## 1. Test Runner & Verification Commands

### Full Bug Bash Suite (161 Tests)
```bash
python3 -m unittest tests/test_e2e_bugbash.py
```
*Current benchmark*: **161 tests run in 4.47s** (all passing, exit code 0).

### Sub-Suite / Tier Execution
```bash
# Tier 1: Feature Coverage (70 tests across 14 features)
python3 -m unittest tests.test_e2e_bugbash.TestTier1FeatureCoverage

# Tier 2: Boundary & Corner Cases (70 tests across 14 features)
python3 -m unittest tests.test_e2e_bugbash.TestTier2BoundaryCases

# Tier 3: Cross-Feature Interactions (14 pairwise interactions)
python3 -m unittest tests.test_e2e_bugbash.TestTier3CrossFeatureInteractions

# Tier 4: Real-World Scenarios (7 realistic application workloads)
python3 -m unittest tests.test_e2e_bugbash.TestTier4RealWorldScenarios
```

### Complete Project Verification Gate
```bash
# Verify entire harness suite including existing tests and new E2E suite
./agyis test
# or
python3 -m harness.cli test
```

---

## 2. 4-Tier Inventory Breakdown

| Tier | Focus Area | Minimum Requirement | Authored Tests | Status |
|------|------------|---------------------|----------------|--------|
| **Tier 1** | Primary Feature Coverage | >=5 tests per feature (14 features = 70) | **70** | ✅ Passed |
| **Tier 2** | Boundary & Corner Cases | >=5 tests per feature (14 features = 70) | **70** | ✅ Passed |
| **Tier 3** | Cross-Feature Interactions | >=14 pairwise cross-cutting combinations | **14** | ✅ Passed |
| **Tier 4** | Real-World Application Workloads | >=7 realistic repository workloads | **7** | ✅ Passed |
| **TOTAL** | Exhaustive E2E Suite | 161 test cases | **161** | ✅ 100% Passing |

---

## 3. Feature Inventory Coverage Mapping

| Feature # | Feature Name in `PROJECT.md` | Tier 1 Tests | Tier 2 Tests | Tier 3 Pairings | Tier 4 Workloads |
|-----------|------------------------------|--------------|--------------|-----------------|------------------|
| **F1** | Harmonization Detection & Migration | `test_t1_f01_01`–`05` | `test_t2_f01_01`–`05` | C01, C05 | S01, S02, S04 |
| **F2** | Harmonization Safety Archiving | `test_t1_f02_01`–`05` | `test_t2_f02_01`–`05` | C01, C02, C12 | S01 |
| **F3** | Tagged Fences & Link Sanitizer | `test_t1_f03_01`–`05` | `test_t2_f03_01`–`05` | C02 | S01 |
| **F4** | Onboard Dirty Tree Guard | `test_t1_f04_01`–`05` | `test_t2_f04_01`–`05` | C03, C12 | S03 |
| **F5** | Pre-Onboard Safety Patch Generation | `test_t1_f05_01`–`05` | `test_t2_f05_01`–`05` | C03, C04 | S02, S03, S04 |
| **F6** | Dedicated Branch Checkout & Cache Purge | `test_t1_f06_01`–`05` | `test_t2_f06_01`–`05` | C04, C06, C13 | S03, S04 |
| **F7** | Monorepo Subproject Targeting | `test_t1_f07_01`–`05` | `test_t2_f07_01`–`05` | C05, C06, C07 | S04 |
| **F8** | DRA Test Runner Audit & Injection | `test_t1_f08_01`–`05` | `test_t2_f08_01`–`05` | C07, C08, C13 | S05, S06 |
| **F9** | Idempotency Verification Cycle | `test_t1_f09_01`–`05` | `test_t2_f09_01`–`05` | C08 | S05, S06 |
| **F10** | SPA Route Switching & Focused Context | `test_t1_f10_01`–`05` | `test_t2_f10_01`–`05` | C09, C11 | S07 |
| **F11** | Subagent Tab Query Param Priority | `test_t1_f11_01`–`05` | `test_t2_f11_01`–`05` | C09, C10 | S07 |
| **F12** | ConnectRPC Streaming Client & RPC Fallback | `test_t1_f12_01`–`05` | `test_t2_f12_01`–`05` | C10, C14 | S07 |
| **F13** | In-Situ CDP Controller Injection | `test_t1_f13_01`–`05` | `test_t2_f13_01`–`05` | C11, C14 | S07 |
| **F14** | CLI Surface Ergonomics & Exit Codes | `test_t1_f14_01`–`05` | `test_t2_f14_01`–`05` | Cross-CLI | S01–S07 |

---

## 4. Discovered Defects Escalated to Orchestrator

The test suite confirmed the presence and edge-case behavior of the following defects:

1. **DEF-BB-006 (Severity: P2)**: Safety patch naming disparity (`wip-safety-pre-onboard.patch` generated in some branches vs canonical `pre_onboard_safety.patch`).
2. **DEF-BB-007 (Severity: P2)**: `harmonize_workspace` requires `prune_legacy=True` to activate `backup=True` safety archiving; running `--apply --backup` without `--prune-legacy` skips archive creation.
3. **DEF-BB-008 (Severity: P2)**: `agyis harmonize [path]` ignores `--apply` flag when the target argument is not the string `"test"`.
4. **DEF-BB-009 (Severity: P3)**: Cargo test harmonization alias injection disparity (`cargo-test` vs `cargo test --`).
5. **DEF-BB-010 (Severity: P1)**: `hotkey.js` route extraction matches `/c/:id` regex before checking `?tab=subagent_convo__<uuid>`, and `commands/gui.py` regex strips query parameters before route resolution.
6. **DEF-BB-011 (Severity: P2)**: HUD mount lifecycle calls unary `loadConversationViaRpc` instead of streaming via `InSituConnectClient.streamConversation`.
7. **DEF-BB-012 (Severity: P3)**: Port fallback hardcoded to `40623` in `hud_rpc.js` when dynamic discovery is absent.
8. **DEF-BB-013 (Severity: P2 - NEW)**: `harness/delivery/cache.py` `_assert_contained` raises `AssertionError: Path containment violation` when `subproject="."` because `resolved == ws_resolved` is not handled as within workspace.
9. **DEF-BB-014 (Severity: P2 - NEW)**: `purge_workspace_build_caches` bounded monorepo traversal in `harness/delivery/cache.py` (line 158) scans the entire workspace rather than bounding cache directory traversal to the specified `subproject` root.

---

## 5. Artifact Reference
- Specification & Tier Architecture: `TEST_INFRA.md`
- Implementation File: `tests/test_e2e_bugbash.py`
- Agent Workspace & Handoff: `.agents/teamwork/teamwork_test_writer_1/`
