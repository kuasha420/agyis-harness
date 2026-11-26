<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# 🗺️ Agyis Harness: Master Product Vision, Contracts & Roadmap
**Project**: Agyis Harness for Google Antigravity™ (`agyis-harness`)  
**Publisher**: Purrfect Software Limited (PSL)  
**License**: Apache-2.0  
**Repository**: `kuasha420/agyis-harness`  
**Last Updated**: 2026-11-25 (`v1.0.0`)  

---

## 1. Product Vision & Core Architectural Contracts

`agyis-harness` is a dual-purpose runtime built strictly on official **Google Antigravity™** surfaces (`plugin.json`, lifecycle hooks, MCP, rules):
1. **The Empirical Laboratory** (`pipeline/`, `data/telemetry.db`, [`empirical-baselines.md`](docs/taxonomy/empirical-baselines.md)): Automated telemetry mining and statistical ground truth across production trajectories.
2. **The Reference Extension Harness** (`harness/`): Zero-dependency standard-library runtime enforcing deterministic protections rather than relying on prompt rules alone.

### Non-Negotiable Contracts
- **Code Enforces, Prompts Guide Cognition**: Runtime PATH/Python `>=3.12` injection (`uv`), `PAGER=cat`, `grep`/`diff` exit-1 sanitization, 2KB output compaction (`39.69%` output volume / `21.31%` context saved), loop breaking, and completion fences live in code hooks; **Codex v2** (`GLOBAL_AGENTS.md` / `AGENTS.md`) governs cognitive discipline via **8** core invariants (`PSL-INV-001`–`008`) plus the on-demand `PSL-RE-001` cleanroom RE pack.
- **3-Tier Coexistence**: Layer 3 Workspace Local (`.agents/`) > Layer 2 User Environment (`~/.gemini/config/`, `~/.gemini/antigravity/`) > Layer 1 Global Plugin (`~/.gemini/config/plugins/agyis-harness/`).
- **Product vs. Project Bifurcation (`ADR-014`)**: Distributable `harness/` never imports from or bundles `pipeline/`, `data/`, `tests/`, or `docs/` (`agyis audit aff`).
- **Hermetic State & Single-Source Hygiene**: Hook state persists under `/tmp/agyis_harness_state_{uid}` (`AGYIS_HARNESS_STATE_DIR` / `PSL_HARNESS_STATE_DIR` override); `.agents/skills/` and `.agents/agents/` mirror `../../harness/` via symlinks (`~4,500` tokens/turn saved).

---

## 2. Active Attention-Horizon & Guardrail Constants (`ADR-033`, `ADR-035`)

Dynamically scaled across **`256k`**, **Gemini 4 (`gemini-4-neon`, `gemini-4-hydrogen`) `512k`**, and **`1M`** context windows (`70%` amber / `90%` red, `80`-step soft epoch horizon `SOFT_EPOCH_STEP_ADVISORY = 80`) and executed by `token_proximity_guard.py` + `pre_invocation_hook.py` (emitting `v2.34.0+` nested `systemMessage` payloads):

| Zone | Scaled Token Runway / Epoch Step Horizon | Runtime Behavior |
| :--- | :--- | :--- |
| **Healthy** | `<70%` scaled window (`<358k` on `512k`, `<180k` on `256k`) and `<80` epoch steps | Nominal execution; zero warning overhead |
| **Amber Warning** | `70%–89.9%` scaled window (`358k–460k` on `512k`) or `>=80` active-epoch steps | Single-shot ANSI warning / non-blocking `systemMessage` epoch horizon advisory |
| **Red Alert / Compaction** | `>=90%` scaled window (`>=460k` on `512k`, `>=230k` on `256k`) | De-spammed `systemMessage` compaction directive, CID-scoped `.agents/artifacts/checkpoints/<conv_id>.md` succession (`agyis checkpoint`), milestone ledger handoff |

---

## 3. Completed Baseline (`v1.0.0` GA — Codex v2, Gemini 4, Antigravity `v2.34.0+` & Public Launch)

Phases 0.5 through **`v1.0.0` GA** (`Horizon 0` empirical ground truth, `Horizon 1` core foundation, `v1.0.0-rc11` bug bash & modular ConnectRPC HUD, **29/29** Antigravity `v2.34.0+` / `agy v1.5.15` / `IDE v2.8.0` / `rea@6.9.0` compatibility fixes across `rc12`–`rc13`, continuous CI & wheel release publishing in `rc14`, and **PSL Invariant Codex v2** `PSL-INV-001`–`008` + `PSL-RE-001` along with full runtime/security/documentation reconciliation for `v1.0.0`) are complete:
- **Verified Surface**: **28** CLI subcommands (`29` parser entries with `changelogs` alias; `router` & `ladder` separate), **30** modular skills (`>100` L ToC, `<24,576` B cap), **8** canonical `v2.34+`/`2.35.2` agent personas (`19` canonical tools `<=20` ceiling), **7** `hooks.json` blocks (**8** `doctor` hook checks), **4** cleanroom RE specifications (including the 29-entry `v2.34.0` drift inventory), **7** official specs, and **4** human runbooks.
- **Verified Quality Gate**: **2,543** hermetic tests (`114` `tests/test_*.py` + `4` `tests/e2e/test_*.py` modules = `118` total), **AFF** architectural fitness gate (`agyis audit aff`, `PSL-INV-008`), **4** cleanroom RE specifications (`agyis verify --spec`), SSOT parity audit (`agyis audit sync-check`), continuous CI (`.github/workflows/ci.yml`), and zero live `config.json` mutation.
- **Release History**: [`CHANGELOG.md`](CHANGELOG.md)
- **Full Historical Ledger (Phases 1–35)**: [`0069329:docs/archive/ledger/project-ledger-rc10-historical.md`](docs/archive/README.md#ledger)
- **Active Post-RC10 Summary & ADRs**: [`docs/taxonomy/project-ledger.md`](docs/taxonomy/project-ledger.md) · [`docs/adr/README.md`](docs/adr/README.md) (`ADR-001`–`ADR-035`)

---

## 4. Post-`v1.0.0` Horizon 2 Priorities

| Priority Track | Scope & Target Deliverables | Acceptance Gate |
| :--- | :--- | :--- |
| **1. `ADR-029` Spatial Terminal Multiplexing** *(Deferred)* | Implement Confluence-mode spatial terminal multiplexing and out-of-band GitHub Discussion coordination (`swarm-council`) per [`docs/adr/README.md`](docs/adr/README.md). | Hermetic router/swarm tests + ADR status promoted from `Deferred` to `Accepted`. |
| **2. Cross-Node Swarm & Publication** | Remote strand telemetry routing and verification across physical Knot mesh nodes (`desktop`, `laptop`, handheld controllers), decoupled worker visual cockpits, and multi-node telemetry sync (`kuasha420/agyis-harness`). | `agyis sync` / `agyis remote triage` verified across strands; strict plugin validation clean. |
| **3. RE & Audit Hardening** | Sustain cleanroom `docs/specs/` verification (`4` cleanroom RE specifications; verified via `agyis verify --spec`), pre-analyzed Ghidra cache ergonomics (`PSL-RE-001`), `100.0/100` AFF fitness (`PSL-INV-008`), SSOT parity (`agyis audit sync-check`), and Gate 2 certification (`agyis audit certify` / `verdict`). | `agyis verify --spec`, `agyis agents validate --json`, `agyis audit aff`, and `agyis audit sync-check` pass with exit `0`. |
