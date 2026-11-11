<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Empirical Telemetry Baselines (Reconciled Post-RC10)

Authoritative ground-truth metrics compiled strictly from `data/*.json`, read-only `data/telemetry.db`, and controlled Issue #83 Route A/B/C experiments. Supersedes standalone legacy taxonomy drafts frozen at commit `0069329` (indexed under [`docs/archive/README.md#taxonomy`](../archive/README.md#taxonomy)).

---

## 1. Corpus Snapshots & Cohort Denominators

| Cohort Source | Sessions (`N`) | Steps | Tool Calls | Tool Errors | Interventions | Preceding Tool Failed |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| Pre-RC5 Audit (`360_telemetry_audit`) | 1,720 | 387,426 | 236,847 | — | 3,270 | 26 (`0.80%`) |
| Failure Classifier (`classified_failures.json`) | 1,734 | 389,329 | 178,747 | 4,132 (`2.31%`) | 3,008 (`1.73/sess`) | — |
| Intervention Summary (`operator_interventions_summary.json`) | — | — | — | — | 3,275 | 26 (`0.79%`) |
| Live DB Snapshot (`data/telemetry.db`, 2026-11-11) | 2,875 | 598,911 | 424,817 | 11,510 (`2.71%`) | 5,604 (`1.95/sess`) | 113 (`2.02%`) |

---

## 2. Context Saturation Cliff, Depth Buckets & Per-Call Refutation

Per-session errors rise sharply past 100k tokens and 200+ steps, whereas **per-call failure probability stays flat around `1.87%–2.80%`**, refuting claims of a 20x–40x per-call tool failure cliff. The session surge reflects cumulative trajectory exposure plus late-stage loop/steering collapse (`14.0x–32.0x` interventions):

| Saturation / Depth Cohort | Sessions (`N`) | Avg Steps | Avg Tokens | Avg Errors / Sess | Avg Interv / Sess | Normalized Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `<20k` tokens (`context_dynamics_summary.json`, `N=1,731`) | 1,032 | 153.8 | 6,473 | 1.26 (`1.0x`) | 1.22 (`1.0x`) | `0.82` errs / 100 steps |
| `20k–50k` tokens (`N=1,731`) | 544 | 232.1 | 32,186 | 2.26 (`1.8x`) | 1.10 (`0.9x`) | `0.97` errs / 100 steps |
| `50k–100k` tokens (`N=1,731`) | 113 | 431.5 | 65,168 | 4.29 (`3.4x`) | 3.01 (`2.5x`) | `0.99` errs / 100 steps |
| `100k–200k` tokens (`N=1,731`) | 28 | 632.6 | 133,418 | 11.14 (`8.8x`) | 9.54 (`7.8x`) | `1.76` errs / 100 steps |
| `200k+` tokens (`N=1,731`) | 14 | 2,707.5 | 651,307 | 57.79 (`45.9x`) | 39.00 (`32.0x`) | `2.13` errs / 100 steps |
| Depth `1–10` steps (`classified_failures.json`, `N=1,734`) | 19 | 4.7 | — | 0.00 | 0.63 | `4.26%` err/call (live DB `N=2,875`) |
| Depth `11–50` steps (`classified_failures.json`, `N=1,734`) | 249 | 31.6 | — | 0.26 | 0.45 | `1.87%` err/call (live DB `N=2,875`) |
| Depth `51–200` steps (`classified_failures.json`, `N=1,734`) | 1,066 | 110.9 | — | 1.44 | 0.35 | `2.80%` err/call (live DB `N=2,875`) |
| Depth `200+` steps (`classified_failures.json`, `N=1,734`) | 400 | 657.8 | — | 6.34 (`24.4x`) | 6.29 (`14.0x`) | `2.70%` err/call (live DB `N=2,875`) |

> **Contradiction Reconciled**: Earlier `N=348` draft prose citing `<50k: 0.8` and `200k+: 31.7` errors/session is superseded by `context_dynamics_summary.json` (`N=1,731`, `44,407,727` tokens) and live `data/telemetry.db` (`N=2,875`). Pre-RC5 DB snapshot (`<=2026-10-18T16:45:06Z`) also confirms flat per-call error rates (`2.07%` at `11–50` vs `2.69%` at `200+`).

---

## 3. Reconciled Contradictions: Reasoning Tiers & Plan-to-Walkthrough Fidelity

Earlier prose claiming `92%+` / `100%` reasoning accuracy (`3.63s` vs `9.26s`) and `75–85%` plan adherence is refuted by the raw audit caches:

| Reasoning Tier (`reasoning_benchmark_results.json`, `N=1,734`) | Sessions (`N`) | Heuristic Acc | Avg Steps | Avg Thinking Tok | Avg Wall-Clock |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `gemini-3.8-flash-low` | 252 | **`46.8%`** | 137.9 | 0 | 1,196.46s |
| `gemini-3.8-flash-high` | 635 | **`46.6%`** | 387.2 | 2,051 | 47,287.14s |
| `gemini-3.1-pro` | 847 | **`35.7%`** | 128.3 | 2,926 | 1,162.47s |

- **Plan-to-Walkthrough Fidelity (`data/artifacts_audit_summary.json`, `N=25` sessions, `45` artifacts)**: Audited `9` `implementation_plan.md` (`0` feedback requested), `2` `walkthrough.md`, and `1` paired session (`8542796b`: `1` planned vs `12` delivered, `0` overlapping files) = **`0.0%` fidelity**.

---

## 4. Failure Taxonomy, Model Clusters, Inventory & Compaction POC

- **Tool Error Hotspots (`classified_failures.json`, `N=1,734`)**: `run_command` (`101,940` calls, `4,629` fails / `4.54%`); `view_file` (`70,039`, `717` / `1.02%`); `replace_file_content` (`14,729`, `110` / `0.75%`). Repeated-call loop candidates total `21,410` (`view_file` `15,780`, `grep_search` `2,145`, `replace_file_content` `1,241`).
- **Exit Code Breakdown (`classified_failures.json`)**: Across `3,217` Exit 1 calls, `619` (`19.24%`) were benign `grep`/`diff` zero-match probes, `472` (`14.67%`) Python tracebacks, and `119` (`3.7%`) syntax errors (`26` Python `<=3.11` f-string backslash errors, `0.81%`). Top structural exits: `2` (`492`), `127` (`204`), `255` (`101`).
- **Tool-Failure Disconnect (`operator_interventions_summary.json`, `N=3,275`)**: `OPERATOR_GUIDANCE` (`2,025`), `CONFIRMATION` (`470`), `STEERING` (`288`), `CONTINUATION` (`225`), `CREDENTIALS` (`202`), `BOOST_ORCHESTRATION` (`33`), `ERROR_RECOVERY` (`26`). Only `26` (`0.79%`) followed a failed tool (`>99.2%` followed technically passing calls).
- **Model Failure Clusters (`model_failure_clusters.json`, `12` models, `88` clusters, `314` steering corrections)**: `gemini-3.8-flash-high` (`482` sess, `158,833` steps, `73,456` calls) logged `0.91%` tool error vs `Gemini 3` (`86` sess, `25,953` calls, `5.03%`) and `gemini-3.6-flash-high` (`16` sess, `1,908` calls, `7.55%`).
- **CoT Perseveration (`N=348` traces)**: `24,163` thinking traces (`15,122,859` chars); session `8d6608ca` (`10,717` steps) spent **`85.5%`** (`1,829 / 2,138`) of traces repeating *"Prioritizing Tool Usage..."* (`281` errors, `201` interventions).
- **Ultra-Deep Titan Sessions (`ultra_deep_sessions_analysis.json`, `N=1,734`)**: `51` titans (`>=1,000` steps) accounted for `132,543` steps (`34.0%` of `389,329` corpus steps), `61,045` calls, `1,103` errors, and `1,342` interventions (`TYPE_A_SURVIVOR`: `21`, `TYPE_B_SYSTEMS_BREAKTHROUGH`: `14`, `TYPE_C_THRASHING_TRAP`: `16`). Live DB has `77` titans.
- **2KB Output Compactor (`volume_distributions.json`, `237,583` calls / `226.2M` out chars)**: Platform truncated `23,483` (`9.88%`) and preserved `6,084` error calls. Compaction saves **`39.69%`** output volume (`89,774,815` chars / `~22.44M` tokens across `43,884` calls; `0` failure-preservation violations) and **`21.31%`** session context (`context_dynamics_summary.json`: `37,855,309` chars across `25,311` steps). POC (`N=348`): `21.29%` (`~6.9M` tok), `<0.25ms` (`241.3 us` at 50KB), `84.5%–96.9%` at `>=10KB`.
- **Customization & Rule Calibration (`customization_inventory.json` & `project_configs_audit.json`, `N=30`)**: `5` MCP servers (`283` tools) consume `263,759` schema tokens vs `1,330` skill-injection tokens (`16` skills: `9` builtin, `7` custom; `41,779` full). Unified rules keep friction low (`psl-agy-harness`: `N=279`, `3.11%` err, `0.27` interv/sess; `<baseline-cli-repo>`: `N=17`, `2.62%` err, `1.94` interv/sess) vs `<client-repo-web>` (`N=6`, `6.27%` err, `39.17` interv/sess).

---

## 5. Controlled Route A / B / C Experiment Scorecard (Issue #83, AC1–AC9)

| Metric (`N=3` Independent Routes) | Route A (`subagent-ladder`) | Route B (`teamwork-preview`) | Route C (Hybrid: Ladder + Boost + Swarm) |
| :--- | :---: | :---: | :---: |
| Net Diff (`total` / `harness/` / `tests/`) | `+852` / `+389` / `+463` (`28` tests) | `+4,068` / `+845` / `+2,357` (`268` tests) | **`+1,153`** / `+491` / `+562` (`36` tests) |
| Subagents / Steps / Total Tokens | `9` / `659` / `24.0M` (`191.0` tok/L) | `36` / `3,525` / `153.6M` (`260.0` tok/L) | **`49` / `4,075` / `~62.6M` (`54.3` tok/L)** |
| Mutation Kill / Battery / Full Suite | `80.95%` / `4.11s` / `13.61s` (`1,406`) | `76.00%` / `100.65s` / `15.46s` (`1,641`) | **`76.00%` / `5.21s` / `13.92s` (`1,414`)** |
| Hook Latency / Residual Gaps / Cleanroom | `<0.05ms` / `4` edge gaps / Sealed | `<1.0ms` / bifurcated hook / Sealed | **`0.0078ms` / `0` gaps / `0/83` DB accesses** |

> **Pink Elephant Cleanroom Verification**: Across `14` SQLite DBs / `3,416` swarm steps in Route C, `<exp-worktree-teamwork-83>` appeared in `83` passive context traces with **`0` active tool accesses** (`100.0%` cleanroom isolation).
