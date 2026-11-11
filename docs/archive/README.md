<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Agyis Harness Frozen Archive Index

- **Frozen Commit Baseline**: **`0069329`** (`docs(rc10): consolidate ADRs, specs, runbooks & taxonomy, remediate runtime gaps, scrub PII, and enforce skill ToCs`)
- **Archived Corpus**: `48` historical Markdown documents across `12` categories, pruned from the active working tree and permanently retrievable from commit `0069329`.
- **Active Replacements**: [ADR Registry](../adr/README.md) · [Empirical Baselines](../taxonomy/empirical-baselines.md) · [Active Project Ledger](../taxonomy/project-ledger.md) · [Platform Surface Mapping](../official-specs/platform-surface-mapping.md) · [User Guide](../user_guide.md) · [Developer Guide](../developer_guide.md)

## Retrieval Commands

```bash
# Inspect any individual frozen archive file directly from commit 0069329
git show 0069329:docs/archive/<subdir>/<file>.md

# Restore the full frozen archive subtree (requires full history or git fetch --unshallow)
git checkout 0069329 -- docs/archive/
```

**Jump to Category**: [`#adr`](#adr) · [`#audits`](#audits) · [`#discussions`](#discussions) · [`#handoffs`](#handoffs) · [`#ledger`](#ledger) · [`#manifests`](#manifests) · [`#official-specs`](#official-specs) · [`#releases`](#releases) · [`#reports`](#reports) · [`#research`](#research) · [`#specs`](#specs) · [`#taxonomy`](#taxonomy)

---

### `adr`
| Era / Date | Topic | Frozen Path (`0069329:docs/archive/`) |
| :--- | :--- | :--- |
| `2026-10-15` (`rc4`) | Opt-in `--experimental-rea` tooling & cleanroom reconstruction (`PSL-ADR-028`) | `adr/ADR-028-opt-in-rea-cleanroom-harmonization.md` |
| `2026-10-05` (`2026-10-06`) | Native `/boost` swarm, `/plan` lock & orchestration alignment | `adr/ADR-031A-native-orchestration-alignment.md` |
| `2026-10-13` | Unified `.agent/` deprecation, decoupled skill presets & fork-aware delivery | `adr/ADR-031B-unified-workspace-harmonization.md` |
| `2026-10-10` | Tool-native primacy & task-log anti-polling invariant (Issue `#32`, PR `#33`) | `adr/ADR-032-tool-native-primacy-and-anti-polling.md` |
| `2026-10-25` (`rc7/rc9`) | `256k/180k/230k` context runway & pre-invocation compaction advisory | `adr/ADR-033-dynamic-context-runway-and-compaction-advisory.md` |
| `2026-10-26` (`rc9`) | Extensible `.agents/commands/` CLI & project command federation (Issue `#100`) | `adr/ADR-034-extensible-workspace-cli.md` |

### `audits`
| Era / Date | Topic | Frozen Path (`0069329:docs/archive/`) |
| :--- | :--- | :--- |
| `2026-10-13` | Agyis installation, harmonization & fleet onboarding gap specification | `audits/agyis-installation-harmonization-gaps.md` |
| `2026-10-18` (`rc4 -> rc5`) | Authoritative fleet upgrade audit matrix & historical pain points | `audits/fleet_audit_rc4.md` |
| `2026-10-16` (`rc5 prep`) | 18-repository cross-verification across 6 core harmonization gaps | `audits/gap_cross_verification_report.md` |
| `2026-10-17` (`rc5`) | Out-of-band adversarial audit of RC5 GitHub issues staging | `audits/out_of_band_rc5_issues_audit.md` |
| `2026-10-17` (`rc5`) | Out-of-band audit of Fleet B Phase 1 Category B core remediations | `audits/out_of_band_rc5_remediations_audit.md` |
| `2026-10-18` (`rc4..main`) | Comprehensive adversarial diff & architectural audit (`v1.0.0-rc4..main`) | `audits/rc4_main_diff_audit.md` |
| `2026-10-16–17` (`rc4`) | Empirical rehydration & fleet rebase findings across RC4 cohort | `audits/rc4_rehydration_findings.md` |
| `2026-11-08` (`rc9..HEAD`) | Cleanroom verification audit of multi-agent subagent router (`1,852` tests) | `audits/subagent_router_audit_report_v1.0.0_rc9_to_head.md` |
| `2026-11-08` (`rc9..HEAD`) | Cleanroom multi-domain teamwork verification audit (`1,852` tests) | `audits/teamwork_audit_report_v1.0.0_rc9_to_head.md` |

### `discussions`
| Era / Date | Topic | Frozen Path (`0069329:docs/archive/`) |
| :--- | :--- | :--- |
| `2026-10` (RC era) | RFC for project rebrand to `agyis` & PSL autonomous ecosystem standardization | `discussions/rebrand-agyis-epic.md` |

### `handoffs`
| Era / Date | Topic | Frozen Path (`0069329:docs/archive/`) |
| :--- | :--- | :--- |
| `2026-10-18` (`rc5`) | Root documentation sync staging diffs & publication drafts | `handoffs/root_sync_staging.md` |
| `2026-10` (`rc5`) | Master successor handoff spec for RC5 agent architecture overhaul (`903` tests) | `handoffs/v1.0.0-rc5-overhaul-handoff.md` |

### `ledger`
| Era / Date | Topic | Frozen Path (`0069329:docs/archive/`) |
| :--- | :--- | :--- |
| `2026-10-02–2026-11-10` (`rc10`) | Historical Horizon 0 & Horizon 1 project ledger (Phases `1–35` verbatim) | `ledger/project-ledger-rc10-historical.md` |

### `manifests`
| Era / Date | Topic | Frozen Path (`0069329:docs/archive/`) |
| :--- | :--- | :--- |
| `2026-10-18` (`rc7`) | Master GitHub issues staging manifest (`#64–#78`, `PSL-MANIFEST-2026-RC7-001`) | `manifests/cognitive_resilience_github_issues_manifest.md` |
| `2026-10-17` (`rc5`) | Master GitHub issues staging manifest for RC5 (`PSL-MANIFEST-2026-RC5-001`) | `manifests/rc5_github_issues_manifest.md` |

### `official-specs`
| Era / Date | Topic | Frozen Path (`0069329:docs/archive/`) |
| :--- | :--- | :--- |
| `2026-10` (`ADR-031A`) | Technical spec for Antigravity native `/boost` & `/plan` primitives | `official-specs/antigravity-boost-and-plan.md` |
| `2026-10` (Superseded) | Legacy `agy` CLI & Python SDK reference (moved to `platform-surface-mapping.md`) | `official-specs/cli-and-sdk.md` |
| `2026-10` (Superseded) | Legacy plugin specification & manifest schema (moved to `platform-surface-mapping.md`) | `official-specs/plugin-manifest.md` |
| `2026-10-15` (`rc4/v1.1.0`) | Harness frictions & Dynamic Repository Awareness (DRA) remediation (`PSL-SPEC-2026-DRA-001`) | `official-specs/remediation-spec-harness-frictions.md` |

### `releases`
| Era / Date | Topic | Frozen Path (`0069329:docs/archive/`) |
| :--- | :--- | :--- |
| `2026-10` (`rc5`) | Legacy RC5 developer guide & technical specifications | `releases/developer_guide_rc5.md` |
| `2026-10` (`rc5`) | Legacy RC5 end-user guide | `releases/user_guide_rc5.md` |
| `2026-10` (`rc4`) | Release notes for `v1.0.0-rc4` (DRA, PR `#40`) | `releases/v1.0.0-rc4.md` |

### `reports`
| Era / Date | Topic | Frozen Path (`0069329:docs/archive/`) |
| :--- | :--- | :--- |
| `2026-10-18` (`rc6`) | 360-degree telemetry audit & emergent pattern mining (`1,720` sessions) | `reports/360_telemetry_audit_2026_10.md` |

### `research`
| Era / Date | Topic | Frozen Path (`0069329:docs/archive/`) |
| :--- | :--- | :--- |
| `2026-10` (RC era) | Index of foundational agentic cognition, runtime & swarm research papers | `research/README.md` |
| `2026-10` (`Jetski 2.24.0`) | Headless discovery & programmatic routing of Antigravity native engines | `research/autonomous_native_protocol_discovery.md` |
| `2026-10-24` | Cognition vs. harness boundaries, protocols & role-pinning (`PSL-ARCH-2026-COGHARN-001`) | `research/cognition_harness_boundary_and_protocols.md` |
| `2026-10` (RC era) | Antigravity customization system, hook lifecycles & runtime contracts | `research/customizations_and_hook_contracts.md` |
| `2026-10` (RC era) | Cleanroom RE blueprint of `/teamwork-preview`, `/boost` (`owl`), and stigmergic IPC | `research/native_multiagent_systems.md` |
| `2026-10` (Issue `#83`) | Controlled 6-Act tri-route experiment (`subagent-ladder` vs `teamwork-preview` vs hybrid) | `research/tri_route_scientific_experiment_report.md` |

### `specs`
| Era / Date | Topic | Frozen Path (`0069329:docs/archive/`) |
| :--- | :--- | :--- |
| `2026-10-17` (`rc5`) | Agent architecture, native orchestration mismatches & delegation overhaul investigation | `specs/agent_overhaul_deep_dive.md` |

### `taxonomy`
| Era / Date | Topic | Frozen Path (`0069329:docs/archive/`) |
| :--- | :--- | :--- |
| `2026-10-02` (Horizon 1 T2) | Tier-2 qualitative cognitive forensics across `14,476` traces (`N=348`) | `taxonomy/cognitive-failure-taxonomy-deepdive.md` |
| `2026-10-18` (Horizon 1 T1) | Tier-1 CoT & thinking trace analysis (`14,476` traces) | `taxonomy/cognitive-traces-report.md` |
| `2026-10-18` (Horizon 1) | Context cliff & token saturation dynamics report (`N=348` snapshot) | `taxonomy/context-cliff-dynamics.md` |
| `2026-10-10` (Horizon 1) | Cross-model failure clusters & intervention hotspots (`N=1,734`) | `taxonomy/model-failure-clusters-report.md` |
| `2026-10-02` (Horizon 1) | `PostToolUse` 2KB output compactor POC benchmark (`N=348`, `19,452` >2KB calls) | `taxonomy/output-compactor-poc-results.md` |
| `2026-10-18` (Horizon 1) | Artifact lifecycle & plan-to-execution drift audit | `taxonomy/planning-and-drift-report.md` |
| `2026-10-21` (Horizon 1) | Project rules (`AGENTS.md`) & `.agents/skills` ecosystem audit | `taxonomy/project-rules-skills-audit.md` |
| `2026-10-18` (`ADR-030`) | Empirical reasoning effort vs. accuracy benchmark matrix | `taxonomy/reasoning-tier-benchmark-report.md` |
| `2026-10-02` (`ADR-003`) | Resolution Gradient Architecture: dynamic aperture & retroactive compaction | `taxonomy/resolution-gradient-architecture.md` |
| `2026-10-18` (Horizon 1) | Tool & command character payload volume distribution report | `taxonomy/tool-volume-distribution-report.md` |
| `2026-10-18` (Horizon 1) | Ultra-deep `1,000+` step titan sessions survival microscope | `taxonomy/ultra-deep-sessions-survival-report.md` |
| `2026-10-18` (Horizon 1) | Workstation empirical telemetry & 4-bucket failure classifier audit | `taxonomy/workstation-audit-report.md` |
