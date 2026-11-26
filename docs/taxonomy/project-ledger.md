<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Agyis Harness Project Ledger (`v1.0.0` GA — Compacted)

> **Archive (`0069329`)**: [`project-ledger-rc10-historical.md`](../archive/README.md#ledger) · **Baselines**: [`empirical-baselines.md`](empirical-baselines.md) · **ADRs (`001–035`)**: [`docs/adr/README.md`](../adr/README.md)

## 1. Current Release Baseline (`v1.0.0` + Wave 1.2 Hardening — 2026-11-26)
- **Verification**: **2,548 hermetic tests** across `114` `tests/test_*.py` + `4` `tests/e2e/test_*.py` modules (`118` total, `python3 -m harness.cli test`), **4** cleanroom specs (`agyis verify --spec`), `agyis audit sync-check` (`PASS`), and `agyis audit aff` (`100.0/100`, `PSL-INV-008`).
- **Surface Inventory**: **28** CLI commands (`29` parser entries incl. `changelogs` alias; `router` & `ladder` separate), **30** modular skills (`>100` L ToC, `<24,576` B cap), **8** `agyis_*` personas (`19` canonical tools `<=20` ceiling / `30` `ANTIGRAVITY_PLATFORM_TOOLS`), **7** `hooks.json` blocks (**8** runner checks), **7** official specs, **4** runbooks.
- **Platform Targets**: Antigravity Desktop `v2.34.0+`, `agy v1.5.15`, `IDE v2.8.0`, `rea@6.9.0` (`255` MCP tools), **Gemini 4** (`gemini-4-neon`, `gemini-4-hydrogen`, `512k`/`1M` scaled runway, `70%`/`90%`, `80`-step soft horizon).
- **Single-Source Hygiene**: `.agents/skills/` and `.agents/agents/` symlink to `../../harness/` (`~4,500` tok/turn saved); active hooks state defaults to `/tmp/agyis_harness_state_{uid}` (`AGYIS_HARNESS_STATE_DIR`).

## 2. Compacted Milestone Chronology (Phases 1–37 -> `v1.0.0` GA)

| Release / Era | Date | Milestone Inflection Summary | Test Baseline |
| :--- | :---: | :--- | :---: |
| **Phases 1–35 (`rc0–rc10`)** | 2026-10-02–11-10 | Telemetry SSOT, hooks (`command-safety`, `anti-loop`, `compactor`, `anti-drift`, `token-proximity`, `pre-invocation`, `completion-fence`), 28-cmd CLI, 30 skills, 8 agents, `ADR-001`–`034`, symlink gate | `1,981` tests |
| **`v1.0.0-rc11` (Ph 36–37)** | 2026-11-15 | Modular ConnectRPC 60 FPS HUD, polyglot `onboard` (#106), 57 bug-bash fixes (`DEF-BB-001..057`), Knot Mesh decoupling (`gh:kuasha420/knot-mesh`), `ADR-035` | `2,356` tests |
| **`v1.0.0-rc12`–`rc14`** | 2026-11-22–23 | **29/29** `v2.34.0` / Gemini 4 / `rea@6.9.0` / ELF RE compat fixes (Epic `#118`), `overwriteResult`, `systemMessage`, Q5 shell guard, `ci.yml` + `uv.lock` wheel releases | `2,486` tests |
| **`v1.0.0` (GA Launch)** | 2026-11-25 | **Codex v2** (`PSL-INV-001`–`008` + `PSL-RE-001`), `<=20` `v2.34+` tools, `agy 1.5.15`, security/runtime hardening (`gui`, `re`, `telemetry`, `aff`, `cli`), full doc reconciliation | `2,441` tests |
| **`v1.1.0` Wave 1.2** | 2026-11-26 | `2.35.2` strict `exa.hooks_pb` wire compat (`wire_compat.py`), SQLite lineage role pinning (`role_lineage.py`), `19`-tool registry + `ROOT_PLAN_MODE_TOOLS`, AFF split + JS bounds, `audit sync-check`, Gate 0 `3,856`-session corpus | `2,502` tests |

## 3. PSL Invariant Codex v2 (`PSL-INV-001`–`008` + `PSL-RE-001`)
1. **`PSL-INV-001`–`003`**: Native exit-0 verification, hermetic `tempfile` tests, stale cache purge; observed-only claims & honest test scopes; zero error swallowing, `|| [ $? -eq 1 ]` probes, surgical `edit_file`, DB port rebind.
2. **`PSL-INV-004`–`006`**: `512k`/`1M` (`70%`/`90%`, `80`-step checkpoint) runway, anti-loop, reactive wait, symlink hygiene; blast-radius `implementation_plan.md`, confirmation gates, `<50`-line ledgers; `author != verifier`, zero coordinator thrash, `<=20` `v2.34+` tools.
3. **`PSL-INV-007`–`008` & `PSL-RE-001`**: Live SPA `/c/:id` & DOM purge; `ADR-014` boundaries, `agyis audit aff`, externalized `assets/`, bounded caches, DAG imports; on-demand `re-ops` cleanroom `.dirtyroom/` & `-noanalysis -readOnly` Ghidra cache.

## 4. Canonical Release Gate Commands & Horizon 2 Status
```bash
python3 -m harness.cli test && python3 -m harness.cli verify --spec && python3 -m harness.cli audit aff
python3 -m harness.cli doctor && python3 -m harness.cli agents validate --json && python3 -m harness.cli rules --lint
```
- **Closed Trackers**: Post-RC10 consolidation, RC11–RC14 `v2.34.0` compat, Codex v2 migration, and `install_workspace()` preset cleanup are complete.
- **Deferred Horizon 2**: Only `ADR-029` (Spatial Terminal Multiplexing) remains explicitly `Deferred` per [`docs/adr/README.md`](../adr/README.md).
