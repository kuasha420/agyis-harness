<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Antigravity Platform Compatibility & Drift Inventory (`v2.34.0`)

- **Document Identifier:** `REA-INV-ANTIGRAVITY-V2_34-2026-11-21`
- **Governing Standards:** ADR-014, ADR-028, Cleanroom Invariants (`PSL-INV-007`), Anti-Vibe (`PSL-INV-010`)
- **Purpose:** Canonical living inventory tracking breaking deltas and compatibility drift between `agyis-harness` (`v1.0.0-rc11`) and the upgraded Google Antigravity platform stack installed on `2026-11-21`.

---

## 1. Audited Platform Surface Baseline (`2026-11-21`)

| Surface | Package / Binary | Installed Version | SHA-256 Digest |
| :--- | :--- | :--- | :--- |
| **Antigravity Desktop Shell** | `antigravity` (`/opt/Antigravity/antigravity`) | `2.34.0-1` (Electron `44.9.1`) | `3ba9114b7fbaafaf548f72c5d1bc86b7dc81098a85361784359c2c1199625bfc` |
| **Antigravity Desktop ASAR** | `/opt/Antigravity/resources/app.asar` | `2.34.0` | `8934adef0622c9271c92eea950a71848764a66f7b10023ccbd82e54b959adb0e` |
| **Jetski Language Server** | `/opt/Antigravity/resources/bin/language_server` | `2.34.0` bundle | `0a044fa38f30dc14363a4450fb0f39f00000834e99b52f12b92ba98b24ad10b9` |
| **Antigravity CLI** | `antigravity-cli` (`/usr/bin/agy`) | `1.5.14` | `37873b8062391b6202a3d3199ec012abc9e53aab720d26cd65699441497d8c94` |
| **Antigravity IDE** | `antigravity-ide` (`/opt/antigravity-ide/bin/antigravity-ide`) | `2.8.0-1` | `5916fa84c6f436635ce1314573bfe860605258867590664c22efd476d353f9207` |

---

## 2. Recorded Discrepancies & Drift Entries (`DRIFT-P0` .. `DRIFT-P3`, 29 Verified Entries)

| Drift ID | Subsystem / Feature | Severity | Status | Impacted `agyis` Files | Verified Platform Evidence & Root Cause |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **`DRIFT-P0-01`** | **Delivery `PluginInstaller` Host Mutation** | `P0` | Verified (Stream 1) | `harness/delivery/installer.py`, `tests/test_delivery.py` | `PluginInstaller.__init__` defaulted `config_dir` to `~/.gemini/config`; `_enable_in_config()` mutated live `config.json` and `test_delivery.py` unlinked live `~/.gemini/antigravity*` symlinks. |
| **`DRIFT-P0-02`** | **Hook Matchers & Uppercase Argument Keys** | `P0` | Verified (Stream 2) | `hooks.json`, `harness/hooks/{anti_drift,completion_fence,anti_loop,command_safety}_hook.py` | Tool matchers omitted `write_file`, `read_file`, `swarm`, `run_workflow`, `mcp_.*` and extractors missed uppercase `Path`/`Content`/`Replacement`. |
| **`DRIFT-P0-03`** | **`PostToolUse` Verification Fence Schema** | `P0` | Verified (Stream 2) | `harness/hooks/{runner,completion_fence_hook,fence_classifiers,fence_tasks}.py` | `runner.py` omitted `hookEventName`; `extract_exit_code` ignored `payload["error"]` and proto3 `result` lacking `exited with code <N>`. |
| **`DRIFT-P0-04`** | **Subagent Platform Tool Allowlist** | `P0` | Verified (Stream 4) | `harness/subagents/{spec,validator,scaffold}.py`, `harness/skills/agent-builder/SKILL.md` | `ANTIGRAVITY_PLATFORM_TOOLS` hardcoded 17 legacy tools and rejected `read_file`, `write_file`, `edit_file`, `swarm`, `run_workflow`, `finish`, etc. |
| **`DRIFT-P0-05`** | **`agyis clean --worktrees` & `--checkpoints`** | `P0` | Verified (Stream 1) | `harness/commands/clean.py` | `--worktrees` forcefully deleted active dirty worktrees and missed UUID worktrees; `--checkpoints` scanned `.agents/artifacts/` instead of `.agents/artifacts/checkpoints/`. |
| **`DRIFT-P0-06`** (`AGY-DRIFT-001`) | **GUI CDP `DevToolsActivePort` Purged on Startup** | `P0` | Remediated (Stream 5) | `harness/commands/gui.py`, `harness/gui/{cdp,launcher,systemd}.py`, `harness/cli_parsers_ops.py` | `v2.34.0` `dist/main.js:372-376` deletes `DevToolsActivePort` without `--remote-debugging-port`. Added live PID detection + restart guidance and `agyis gui --install-launcher`. |
| **`DRIFT-P1-01`** | **Agent Definitions Tool Starvation (`agyis_*.md`)** | `P1` | Verified (Stream 4) | `harness/agents/agyis_*.md`, `.agents/agents/agyis_*.md` | `agyis_*.md` declared retired tools (`list_dir`, `grep_search`, `find_by_name`, `read_url_content`), starving `agyis_reviewer`, `agyis_coordinator`, `agyis_planner`. |
| **`DRIFT-P1-02`** | **Presence Locks, `conversation_summaries.db`, `/swarm` Lineage** | `P1` | Verified (Stream 3/4) | `harness/utils/context.py`, `harness/trajectory/transcript_reader.py`, `harness/subagents/{context,liveness}.py`, `harness/commands/{checkpoint,cockpit}.py` | Blind to `presence/*.lock`, `conversation_summaries.db`, `swarm{action:"add"}`, and `post_message+swarm_wait`; `checkpoint status` leaked 43 unrelated sessions. |
| **`DRIFT-P1-03`** | **Protobuf `ModelUsageStats` & `TokenType` 8..10** | `P1` | Verified (Stream 3) | `harness/trajectory/protobuf.py` | Swapped `output_tokens` (`fn=10`) / `thought_tokens` (`fn=9`) and dropped `TokenType` 8..10 (`WORKFLOWS`, `PLUGINS`, `FLOWS`). |
| **`DRIFT-P1-04`** | **SQLite `step_type` Shift & `harvest_conversations.py`** | `P1` | Verified (Stream 3) | `harness/trajectory/{sqlite_reader,protobuf}.py`, `pipeline/harvest_conversations.py` | `132 GENERIC`, `101 SYSTEM_MESSAGE`, `fn=29 modified_tool_call`; `harvest_conversations.py` opened live DBs RW and misparsed `fn=18`. |
| **`DRIFT-P1-05`** | **Transcript Extraction & Rehydration `v2.34.0` Fields** | `P1` | Verified (Stream 3/4) | `harness/telemetry/{extractor,db}.py`, `harness/subagents/rehydrate.py`, `pipeline/extract_transcripts.py` | Missed `Path`/`Target`/`Replacement`/`Content`/`model`, bypassed `transcript_full.jsonl`, and mispaired multi-tool steps. |
| **`DRIFT-P1-06`** | **`agy` CLI (`antigravity-cli`) App Data Dir** | `P1` | Verified (Stream 3) | `harness/trajectory/sqlite_reader.py`, `harness/telemetry/db.py`, `pipeline/*` | `get_conversations_dir()` ignored `ANTIGRAVITY_APP_DATA_DIR` and `~/.gemini/antigravity-cli/`. |
| **`DRIFT-P1-07`** | **512k/1M Context Window Defaults** | `P1` | Verified (Stream 3) | `harness/trajectory/health.py`, `harness/commands/checkpoint.py`, `harness/delivery/compaction_checkpoint.py` | Defaulted Gemini 3.8/4 models to `256_000` when optional proto3 `max_context_tokens` was omitted. |
| **`DRIFT-P1-08`** | **`psl-output-compactor` `overwriteResult` & `read_file`** | `P1` | Verified (Stream 2) | `hooks.json`, `harness/hooks/{output_compactor_hook,runner}.py` | Emitted `{}` instead of `{"overwriteResult": compacted}` and omitted `read_file` from matcher. |
| **`DRIFT-P1-09`** | **3-Tier Coexistence & Duplicate `always_on` Rules** | `P1` | Verified (Stream 1) | `harness/delivery/{copy_install,coexistence,constants,surfaces,installer}.py`, `harness/rules/*` | `copy_install.py` installed `GLOBAL_AGENTS.md` twice (`AGENTS.md` + `GLOBAL_AGENTS.md`); `coexistence.py` hardcoded `~/.gemini/antigravity/`. |
| **`DRIFT-P1-10`** | **`onboard --dry-run` Mutation & CLI Shadowing** | `P1` | Verified (Stream 1) | `harness/commands/onboard.py`, `harness/delivery/{git_topology,surfaces}.py`, `harness/cli.py` | `onboard --dry-run` ran `gh repo fork`, step 12 wiped workspace skills, and `.agents/commands/*` shadowed built-in `agyis` commands. |
| **`DRIFT-P1-11`** (`AGY-DRIFT-002`, `003`) | **In-Situ HUD (`hud_rpc.js`, `hotkey.js`, `hud.js`) vs `v2.34.0`** | `P1` | Remediated (Stream 5) | `harness/gui/assets/{hud_rpc,hotkey,hud}.js`, `harness/gui/trajectory_hud.py`, `harness/commands/gui.py`, `harness/cli_parsers_ops.py` | Added `localStorage["agy_session_csrf_token"]` fallback, `trajectoryVerbosity: 3`, singular `executorMetadata`, `update.contextWindowUsage`, `cwm.maxContextTokens`, `TokenType 8-10`, `CortexStepType.GENERIC (132)`, `__agyis_hud_mount` + DOM reattach, `/c/<id1>+<id2>?focused=<id2>` parsing, and removed `?trajectoryDebugOpen=true` / Command Palette claims. |
| **`DRIFT-P1-12`** | **`agyis verify --scaffold` & `rea@6.9.0` Schema / False-Green** | `P1` | Remediated (Stream 5) | `harness/cleanroom/obligation.py`, `harness/commands/verify.py`, `harness/cli_parsers_core.py` | Aligned `ReviewedObligation` (18 strictObject fields) & `scaffold_obligation_ledger` (`providers: []` with `records: []`) with `rea@6.9.0`; `verify` now fails non-zero on missing ledger or REA timeout/error. |
| **`DRIFT-P1-13`** | **Linux ELF64/ELF32 Support in `agyis re` (`addr`, `xrefs`, `preanalyze`)** | `P1` | Remediated (Stream 5) | `harness/re/{address,xrefs,preanalyze,priming,scaffold}.py`, `harness/commands/re.py` | Added pure-stdlib ELF64/ELF32 section/VA/RVA/file-offset parser (`parse_elf_sections` / `parse_binary_sections`), ELF magic format detection, `objdump -T/-t` fallback, and extensionless executable priority. |
| **`DRIFT-P1-14`** | **`cockpit verify` Scoping & `find_active_plan` Env Vars** | `P1` | Verified (Stream 3/4) | `harness/commands/cockpit.py`, `harness/utils/plan_parser.py` | `cockpit verify` accepted stale unscoped checkpoints; `find_active_plan` ignored `ANTIGRAVITY_CONVERSATION_ID` / `ANTIGRAVITY_APP_DATA_DIR`. |
| **`DRIFT-P2-01`** | **`sync.py` ADR-014 Exemption & `sessions.total_tokens_est`** | `P2` | Verified (Stream 3) | `harness/commands/sync.py`, `harness/hooks/token_proximity_guard.py` | `sync.py` imported `pipeline/*`; `token_proximity_guard.py` queried nonexistent `sessions.total_tokens_est`. |
| **`DRIFT-P2-02`** | **`pre_invocation_hook.py` & `StopHookArgs.continuationActive`** | `P2` | Verified (Stream 2) | `harness/hooks/{pre_invocation_hook,role_pinning,fence_state,completion_fence_hook}.py` | Emitted deprecated `ephemeralMessage`, hardcoded `~/.gemini/antigravity/brain`, and ignored `continuationActive`. |
| **`DRIFT-P2-03`** | **Agent Frontmatter, `/teamwork` Root & Skills Discovery** | `P2` | Verified (Stream 4) | `harness/subagents/{spec,scaffold,liveness,heartbeat,routing}.py`, `harness/skills/__init__.py`, `harness/commands/agents.py` | `permissions.*` drift, `/teamwork` hardcoded to `.agents/teamwork/`, `skills/__init__.py` missed builtin/global skills, `agents validate --json` ignored `--json`. |
| **`DRIFT-P2-04`** | **`agyis doctor --heal`, `harmonize`, & `ANTIGRAVITY_SSH_BIN`** | `P2` | Verified (Stream 1) | `harness/runtime/{doctor,healing,hygiene_checks,tool_checks_rea}.py`, `harness/delivery/harmonize.py`, `harness/remote/runner.py` | `doctor` inflated `ok` count, `healing.py` no-oped on 5 categories, `harmonize` missed `_agents/`, `remote` ignored `ANTIGRAVITY_SSH_BIN`. |
| **`DRIFT-P2-05`** | **HUD `Escape` / `browserWcv` / `TrajectoryServer` / LS 401 / `rea_mcp.sock` / Docs** | `P2` | Remediated (Stream 5) | `harness/gui/assets/hotkey.js`, `harness/gui/{cdp,server}.py`, `harness/commands/gui.py`, `harness/re/daemon.py`, `docs/specs/*` | Deduplicated `Escape` handling, filtered `browserWcv` / `:40624` in `find_page_target`, propagated `brain_dir` & `parent_id` + `transcript_full.jsonl` mtime in `server.py`, verified JSON/Connect `Content-Type` on HTTP 400/401 LS probes, bound `rea_mcp.sock` in `daemon.py`. |
| **`DRIFT-P2-06`** | **`discovery.py` Non-Interactive Env & `pipeline/*` Drift** | `P2` | Verified (Stream 3) | `harness/discovery.py`, `harness/utils/plan_parser.py`, `harness/commands/status.py`, `pipeline/*` | Checked `ANTIGRAVITY` instead of `ANTIGRAVITY_AGENT`, legacy `EXCLUDED_WORDS`, `256k` fallback, `ChatStartMetadata.start_step_index` mapping. |
| **`DRIFT-P3-01`** | **`plugin.json` `license`/`keywords` Fields** | `P3` | Verified (Stream 1) | `plugin.json`, `harness/plugin.json` | Included `license` and `keywords` fields silently discarded by Antigravity plugin loader. |
| **`DRIFT-P3-02`** | **`CSS.escape()`, `hud_header.js:109`, `patcher.py` 12.2, RE Test Isolation** | `P3` | Remediated (Stream 5) | `harness/gui/assets/{hud,hud_header}.js`, `harness/re/patcher.py`, `tests/test_re_toolchain.py` | Added `CSS.escape()` in `hud.js`, replaced undefined Tailwind classes in `hud_header.js:109`, distinguished `policy_native` in `patcher.py`, isolated `test_cmd_decompile_*` from repo `.dirtyroom/cache/stats.json`. |
| **`DRIFT-P3-03`** | **`.agents/agents/__init__.py` Sync Parity** | `P3` | Verified (Stream 4) | `harness/subagents/spec.py`, `.agents/agents/__init__.py` | `sync_agent_definitions` only copied `*.md`, leaving `.agents/agents/__init__.py` out of sync. |

---

## 3. Holistic Swarm Sweep Coverage Matrix

| Workstream Owner | Subsystem Scope | Audit Status |
| :--- | :--- | :--- |
| `audit-hooks` | `hooks.json`, `harness/hooks/*`, `harness/rules/*` vs. `v2.34.0` / `agy 1.5.14` native tool names & hook schemas | Completed (`#12`, `#14`) |
| `audit-trajectory` | `harness/trajectory/*`, `harness/telemetry/*`, `pipeline/*`, `sync`, `audit`, `status`, `checkpoint` vs. live SQLite/protobuf/transcripts | Completed (`#9`, `#14`) |
| `audit-agents` | `harness/subagents/*`, `harness/agents/*`, `harness/skills/*`, `cockpit`, `router`, `subagents` vs. `v2.34.0` native tools, `/swarm`, builtin skills & slash commands | Completed (`#13`, `#14`) |
| `audit-surfaces` | `harness/delivery/*`, `harness/harmonize/*`, `harness/doctor/*`, `harness/remote/*`, `harness/runtime/*`, `onboard`, `init`, `install`, `clean`, `ext` vs. `v2.34.0` / `agy 1.5.14` / `antigravity-ide 2.8.0` | Completed (`#10`, `#14`) |
| `audit-gui-re` | `harness/gui/*`, `harness/re/*`, `harness/cleanroom/*`, `gui`, `re`, `verify` vs. `v2.34.0` `BaseWindow`/`WebContentsView`, HUD assets & `rea` tooling | Completed (`#11`, `#14`) — Remediated in Stream 5 |
| `verifier` | Independent empirical cross-check, test suite / AFF / `verify --spec` baseline, and consolidated severity-ranked triage | Completed (`#14`) |
