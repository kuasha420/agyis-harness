<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# 🗺️ Agyis Harness: Master Product Vision, Contracts & Roadmap
**Project**: Agyis Harness for Google Antigravity™ (`agyis-harness`)  
**Publisher**: Purrfect Software Limited (PSL)  
**License**: Apache-2.0  
**Repository**: `kuasha420/agyis-harness` (Private Development → Public Release)  
**Last Updated**: 2026-11-12  

---

## 1. Product Vision & Core Architectural Contracts

`agyis-harness` is a dual-purpose runtime built strictly on official **Google Antigravity™** surfaces (`plugin.json`, lifecycle hooks, MCP, rules):
1. **The Empirical Laboratory** (`pipeline/`, `data/telemetry.db`, [`empirical-baselines.md`](docs/taxonomy/empirical-baselines.md)): Automated telemetry mining and statistical ground truth across production trajectories.
2. **The Reference Extension Harness** (`harness/`): Zero-dependency standard-library runtime enforcing deterministic protections rather than relying on prompt rules alone.

### Non-Negotiable Contracts
- **Code Enforces, Prompts Guide Cognition**: Runtime PATH/Python `>=3.12` injection (`uv`), `PAGER=cat`, `grep`/`diff` exit-1 sanitization, 2KB output compaction (`39.69%` output volume / `21.31%` context saved), loop breaking, and completion fences live in code hooks; `AGENTS.md` governs cognitive discipline (`PSL-INV-001`–`011`).
- **3-Tier Coexistence**: Layer 3 Workspace Local (`.agents/`) > Layer 2 User Environment (`~/.gemini/config/`, `~/.gemini/antigravity/`) > Layer 1 Global Plugin (`~/.gemini/config/plugins/agyis-harness/`).
- **Product vs. Project Bifurcation (`ADR-014`)**: Distributable `harness/` never imports from or bundles `pipeline/`, `data/`, `tests/`, or `docs/` (`agyis audit aff`).
- **Hermetic State & Single-Source Hygiene**: Hook state persists under `/tmp/agyis_harness_state_{uid}` (`AGYIS_HARNESS_STATE_DIR` / `PSL_HARNESS_STATE_DIR` override); `.agents/skills/` mirrors symlink to `../../harness/skills/` (`~4,500` tokens/turn saved).

---

## 2. Active Attention-Horizon & Guardrail Constants (`ADR-033`)

Calibrated on a **256k** token context window (`CONTEXT_WINDOW_TOKENS = 256_000`, empirical compaction trigger avg `245,941`) and executed by `token_proximity_guard.py` + `pre_invocation_hook.py`:

| Zone | Token Runway / Epoch Step Horizon (`256k` baseline) | Runtime Behavior |
| :--- | :--- | :--- |
| **Healthy** | `<70%` scaled window (`<180k` on `256k`) and `<80` epoch steps | Nominal execution; zero warning overhead |
| **Amber Warning** | `70%–89.9%` scaled window (`180k–229,999` on `256k`) or `>=80` active-epoch steps | Single-shot ANSI warning / non-blocking epoch horizon advisory |
| **Red Alert / Compaction** | `>=90%` scaled window (`>=230k` on `256k`) | De-spammed compaction directive, CID-scoped `.agents/artifacts/checkpoints/<conv_id>.md` succession (`agyis checkpoint`), milestone ledger handoff |

---

## 3. Completed Baseline (`v1.0.0-rc10` — Phases 0.5–35)

Phases 0.5 through 35 (`Horizon 0` empirical ground truth and `Horizon 1` product foundation through `v1.0.0-rc10`) are complete and permanently compacted out of active roadmap context:
- **Verified Surface**: **28** CLI subcommands (`router` & `ladder` separate), **30** modular skills (`>100` L ToC, `<24,576` B cap), **8** agent personas, **7** `hooks.json` blocks (**8** `doctor` hook checks), **3** cleanroom RE specifications (**19** verified empirical evidence rows: `10` SHA-256 `ev_*` digests + `9` `EV-20261017` runtime checks), **7** official specs, and **3** human runbooks.
- **Verified Quality Gate**: **1,993** hermetic tests, **100.0/100 AFF** score (`agyis audit aff`), and **3** cleanroom RE specifications (`19` verified empirical evidence rows: `10` SHA-256 `ev_*` digests + `9` `EV-20261017` runtime checks; verified via `agyis verify --spec`).
- **Release History**: [`CHANGELOG.md`](CHANGELOG.md)
- **Full Historical Ledger (Phases 1–35)**: [`0069329:docs/archive/ledger/project-ledger-rc10-historical.md`](docs/archive/README.md#ledger)
- **Active Post-RC10 Summary & ADRs**: [`docs/taxonomy/project-ledger.md`](docs/taxonomy/project-ledger.md) · [`docs/adr/README.md`](docs/adr/README.md) (`ADR-001`–`ADR-035`)

---

## 4. Post-RC10 Horizon 2 Priorities

| Priority Track | Scope & Target Deliverables | Acceptance Gate |
| :--- | :--- | :--- |
| **1. `ADR-029` Spatial Terminal Multiplexing** *(Deferred)* | Implement Confluence-mode spatial terminal multiplexing and out-of-band GitHub Discussion coordination (`swarm-council`) per [`docs/adr/README.md`](docs/adr/README.md). | Hermetic router/swarm tests + ADR status promoted from `Deferred` to `Accepted`. |
| **2. Cross-Node Swarm & Publication** | Remote strand telemetry routing and verification across physical Knot mesh nodes (`desktop`, `laptop`, handheld controllers), decoupled worker visual cockpits, and public release readiness (`kuasha420/agyis-harness`). | `agyis sync` / `agyis remote triage` verified across strands; strict plugin validation clean. |
| **3. RE & Audit Hardening** | Sustain cleanroom `docs/specs/` verification (`3` cleanroom RE specifications, `19` verified empirical evidence rows: `10` SHA-256 `ev_*` digests + `9` `EV-20261017` runtime checks; verified via `agyis verify --spec`), pre-analyzed Ghidra cache ergonomics (`PSL-INV-009`), `100.0/100` AFF fitness (`PSL-INV-011`), and Gate 2 certification (`agyis audit certify` / `verdict`). | `agyis verify --spec`, `agyis verify`, and `agyis audit aff` pass with exit `0`. |
| **4. Remaining `install_workspace()` Fallback Cleanup** | Migrate `install_workspace()` in `harness/delivery/workspace.py` off the remaining `STACK_SKILL_PRESETS` fallback onto the decoupled language-runtime + architectural-role resolver already wired into `agyis onboard` and `agyis harmonize` (`ADR-031B`). | `init` / `install -w` parity tests pass with zero `STACK_SKILL_PRESETS` dependency. |
