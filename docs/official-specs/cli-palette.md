<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Official Specification: Consolidated 27-Command CLI Palette

**Document**: Canonical CLI Subcommand Palette & Reference Guide  
**Project**: Agyis Harness for Google Antigravity™ (`agyis-harness`)  
**Publisher**: Purrfect Software Limited (PSL)  
**License**: Apache-2.0  
**Binary Entrypoint**: `agyis` (Primary) / `psl` (Deprecated Alias) / `python3 -m harness.cli`  
**Last Updated**: 2026-11-11  

---

## 1. Executive Overview

The unified developer CLI (`agyis` or `python3 -m harness.cli`, with backward-compatible alias `psl`) exposes 27 top-level subcommands (plus canonical aliases) implemented cleanly across `harness/commands/`, `harness/delivery/`, `harness/subagents/`, `harness/remote/`, and `harness/telemetry/`. In accordance with ADR-014 (Product vs. Project Bifurcation), all core CLI commands execute hermetically with zero mandatory dependencies on external third-party Python packages.

> [!NOTE]
> **CLI Nomenclature & Deprecation Lifecycle**: `agyis` is the primary executable. The legacy command `psl` is maintained as a backward-compatible alias with an active deprecation lifecycle (emitting `DeprecationWarning: 'psl' is deprecated and will be removed in 3 months. Use 'agyis' instead.` to `stderr`).

```text
agyis [-h] [-v]
  ├── doctor        Audit host workstation runtimes, port collisions, RE toolchain, and auto-heal
  ├── hook          Run a lifecycle hook handler directly via fail-safe runner
  ├── test          Run hermetic test suites with diff-aware filtering & benchmark timing
  ├── audit         Run empirical telemetry laboratory extraction, certification & AFF audit
  ├── rules         Audit, deduplicate, and harmonize global & workspace agent rule files
  ├── skills        List, inspect, synchronize, and deduplicate modular skills
  ├── agents        Catalog, inspect, create, validate, and rehydrate specialist subagents
  ├── subagents     List active subagents, liveness status, and live context health gauges
  ├── status        Print harness health, active hooks, attention horizon & telemetry summary
  ├── remote        Remote agentic execution, SSH multiplexing & cloud/mesh triage (ADR-027)
  ├── auth          Manage GitHub organization authentication for central hub sync
  ├── sync          Bi-directional telemetry sync and native background systemd daemon (ADR-030)
  ├── init          Initialize workspace project with stack skills, tagged rules & cleanroom ledgers
  ├── harmonize     Harmonize legacy .agent/ directories and PSL-HARNESS rules into .agents/
  ├── onboard       Unified brownfield workspace onboarding with branch isolation, cache purge & PR delivery
  ├── install       Install Agyis harness globally as Google Antigravity plugin across surfaces
  ├── uninstall     Uninstall Agyis harness global plugin cleanly without collateral damage
  ├── verify        Formally verify cleanroom specifications and REA reconstruction manifests (ADR-028)
  ├── gui           Introspect and control Antigravity Electron GUI via CDP WebSocket (ADR-014)
  ├── release-notes Parse conventional commits and generate structured release notes
  ├── changelog     Generate, update, or backfill Keep-a-Changelog entries (alias: changelogs)
  ├── checkpoint    Carrier-grade pre-compaction state capture & session succession (ADR-031A, ADR-033)
  ├── cockpit       Cockpit Flight Director pairing dashboard & 12-workflow router (ADR-031A)
  ├── router        Dynamic subagent router across canonical workflows (alias: ladder)
  ├── clean         Multi-branch workspace hygiene, worktree pruning & build artifact removal (ADR-031A, ADR-031B)
  ├── re            Cleanroom reverse engineering toolsuite & Ghidra acceleration (ADR-028, ADR-034)
  └── ext           Extensible workspace CLI command runner & scaffolding suite (ADR-034)
```

---

## 2. Detailed Subcommand Reference

### 1. `doctor`
* **Syntax**: `agyis doctor [--matrix <path>] [--heal] [--experimental-rea] [--json]`
* **Purpose**: Audits the host environment against the 3-tier runtime compatibility matrix ([matrix.json](../../matrix.json)):
  - **Tier 1 (Languages/Packaging)**: Python >= 3.12 (PEP 701 f-strings), Node >= 20, `uv`, `pnpm`.
  - **Tier 2 (Core SWE CLI)**: `git >= 2.38`, `gh >= 2.30`, `ripgrep >= 13.0`, `fd >= 8.7`.
  - **Tier 3 (Mesh Host)**: `ssh >= 8.9`, `knot >= 1.0`.
  - **Port Collision Probing**: Probes TCP port 5432 to identify foreign container collisions and recommends dynamic port re-binding.
* **Flags**:
  - `--matrix <path>`: Custom path to runtime matrix configuration (defaults to `harness/runtime/matrix.json`).
  - `--heal`: Executes safe zero-sudo user-space auto-healing via `uv` (provisions certified CPython >= 3.12).
  - `--experimental-rea`: Audits Reverse Engineer Anything (REA >= 6.0.0), MCP server registration, dynamic JDK 21+ discovery ladder, Ghidra 12.1+ headless analyzer, and Hopper display socket contracts.
  - `--json`: Emits complete diagnostic audit report in structured JSON format.
* **Exit Codes**: `0` on clean environment or successful auto-heal; `1` if missing/outdated runtimes remain.

### 2. `hook`
* **Syntax**: `agyis hook <hook_name>`
* **Purpose**: Directly executes a lifecycle hook handler, reading the Antigravity protojson payload from `stdin` and emitting protojson on `stdout`.
* **Accepted Hook Names & Aliases**:
  - `command-safety` (alias: `safety`)
  - `anti-loop` (alias: `loop`)
  - `output-compactor` (alias: `compactor`)
  - `verification-fence` (aliases: `fence`, `stop-fence`, `stop`, `completion-fence`)
  - `anti-drift` (aliases: `drift`, `anti_drift`)
  - `token-proximity` (aliases: `token-proximity-guard`, `token`, `token_proximity_guard`)
  - `pre-invocation` (aliases: `preinvocation`, `compaction-advisory`, `compaction_advisory`, `compaction`, `advisory`)
* **Behavior**: Delegates to `harness.hooks.runner.run_hook()`, providing fail-open deadlock protection (`{"decision": "allow"}` or `{}` / `{"injectSteps": []}`).

### 3. `test`
* **Syntax**: `agyis test [-v|--verbose] [-s|--start-dir <path>]`
* **Purpose**: Executes the project test suite, measures benchmark execution time against the <1.0s benchmark invariant, and clears verification fence flags on success.
* **Flags**:
  - `-v`, `--verbose`: Enables detailed individual test case reporting.
  - `-s`, `--start-dir <path>`: Directory containing test suites (defaults to `tests/`).
* **Side Effects**: Upon zero exit code, sweeps `$AGYIS_HARNESS_STATE_DIR/verification_state_*.json` (or `$PSL_HARNESS_STATE_DIR`), setting `code_dirty = False` and `block_count = 0` to unlock agent completion.

### 4. `audit`
* **Syntax**: `agyis audit [stage] [options]`
* **Purpose**: Runs empirical telemetry laboratory pipelines against local or federated databases (`data/telemetry.db`). Lazy-imports development stages from `pipeline/` on demand.
* **Stages**:
  - `all` (default): Runs extract, classify, inventory, dynamics, traces, interventions, volume, clusters.
  - `extract`: Ingests raw `transcript.jsonl` from `~/.gemini/antigravity/brain/` into `data/telemetry.db`.
  - `benchmark`: Executes reasoning tier latency vs. accuracy benchmark.
  - `classify`: Categorizes trajectories into WHAT_WORKED and WHAT_FAILED taxonomy buckets.
  - `inventory`: Catalogs plugins, skills, rules, hooks, and MCP servers across workspaces.
  - `dynamics`: Computes context saturation and step-count degradation curves.
  - `traces`: Extracts Chain-of-Thought thinking traces and identifies cognitive failure modes.
  - `interventions`: Aggregates operator rescue and steering prompts.
  - `volume`: Audits tool output and input character volume distributions.
  - `deep`: Mines ultra-deep sessions (>=1,000 steps) and survival archetypes.
  - `session`: Detailed forensic audit of a single session UUID (`-s <session_id>`).
  - `live`: Real-time active session inspector.
  - `clusters`: Mined cross-model failure clusters and intervention hotspots.
  - `artifacts` / `configs` / `project-configs`: Audits workspace/plugin artifacts, configurations, and per-project overrides (also accepts `project_configs`).
  - `prune`: Prunes older telemetry sessions beyond `--days` (`--dry-run` supported).
  - `certify` / `verdict`: Runs full suite + doctor audit to issue/inspect out-of-band `audit_verdict.json` (Gate 2).
  - `aff` (aliases: `macro`, `fitness`): Evaluates automated architectural fitness, module boundaries, and dependency acyclicity (PSL-INV-011).
* **Key Flags**: `--db <path>`, `--conv-dir <path>`, `--backfill`, `-s|--session-id <id>`, `--save-db`, `--out <path>`, `--json`, `--output-json <path>`, `--output-report <path>`, `--quiet`, `--days <N>`, `--dry-run`, `--task-id <id>`, `--verdict <verdict>`, `--skip-tests`, `--workspace <path>`.

### 5. `skills`
* **Syntax**: `agyis skills [name] [--sync] [--prune-duplicates] [-g|--group <grp>] [-s|--stack <stk>] [--skills <list>] [--override] [--json]`
* **Purpose**: Discovers, inspects, synchronizes, and deduplicates modular product skills globally or tailored to a project workspace.
* **Flags & Options**:
  - `name`: Specific skill identifier to inspect or synchronize (e.g. `psl-stack-python`, `media-ops`, `subagent-ladder`).
  - `--sync`: Synchronizes skills from `harness/skills/` to target workspace `.agents/skills/`.
  - `--prune-duplicates`: Deduplicates workspace skills that duplicate global plugin skills (saving ~4,500 tokens/turn).
  - `-s`, `--stack <stk>`: Tailors deployment to a specific stack preset (`python`, `typescript`, `rust`, `go`, `systems`, `shell`, `backend`, `auto`). `--stack auto` detects stack from repository manifests (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`).
  - `-g`, `--group <grp>`: Syncs a functional group preset (`stack`, `testing` / `runners`, `ops` / `workstation`, `workflow` / `ladder`).
  - `--skills <list>`: Comma-separated list of specific skill names to synchronize.
  - `--override`: Overwrites existing local skill files even if identical.
  - `--json`: Emits complete skill catalog and metadata in JSON format.

### 6. `agents`
* **Syntax**: `agyis agents [name|action] [target] [options]`
* **Purpose**: Lists, inspects, scaffolds, validates, or rehydrates specialist subagent personas.
* **Sub-Actions**:
  - `agyis agents`: Lists all 8 registered specialist subagents.
  - `agyis agents <name>`: Inspects agent specification, permissions, tools, and archetype.
  - `agyis agents create <name> -a <archetype> -b <bundle> [--scope project|global]`: Scaffolds verified agent definition.
  - `agyis agents validate [file_or_name]`: Validates YAML frontmatter, tool allowlists, and hanging bug defenses.
  - `agyis agents rehydrate --id <conv_id>`: Reconstructs agent conversation context from disk.
  - `agyis agents --sync`: Synchronizes agent definitions from `harness/agents/` to `.agents/agents/`.
* **Key Flags**: `-a|--archetype`, `-b|--bundle`, `--scope`, `-m|--model`, `--id`, `--recent-hours`, `--brain-dir`.

### 7. `subagents`
* **Syntax**: `agyis subagents [--json] [--brain-dir <path>]`
* **Purpose**: Renders a formatted ASCII table of active subagents, estimating step count, character volume, token consumption, and context health zone (`HEALTHY/REUSE`, `AMBER/COMPACT_RECREATE`, `RED_ALERT/RETIRE`) in microseconds without API token overhead.

### 8. `status`
* **Syntax**: `agyis status`
* **Purpose**: Prints a unified system status dashboard:
  - Repository & working tree status.
  - Active lifecycle hooks in `hooks.json`.
  - Cognitive Attention Horizon Gauge & active plan boundaries.
  - Modular skills catalog count & mirror synchronization status.
  - Specialist subagents catalog & live active subagents health table.

### 9. `remote`
* **Syntax**: `agyis remote <subcommand> [args]`
* **Purpose**: Manages remote agentic execution over multiplexed SSH (ADR-027).
* **Subcommands**:
  - `exec <target> "<cmd>" [-p <port>] [-l|--login-shell] [-t <timeout>]`: Executes command over OpenSSH ControlMaster socket; optional login shell wrapping (`bash -l -c`) for user toolchains.
  - `script <target> <file> [--stage] [-p <port>] [-t <timeout>] [args...]`: Streams local script to remote target via stdin (zero disk footprint) or stages with trap cleanup.
  - `triage <target> [--profile all|ports|services|resources|logs] [--service <svc>] [-n <lines>] [--json]`: Gathers compact (<2KB) health report across OS metrics.
  - `socket status`: Lists active OpenSSH ControlMaster sockets in `~/.cache/agyis/ssh/` (or `~/.cache/psl/ssh/`).
  - `socket cleanup`: Closes and unlinks active ControlMaster multiplexing sockets.
  - `screens [--brain-dir <dir>] [--data <json>] [--json]`: Generates fleet screens carousel artifact.

### 10. `auth`
* **Syntax**: `agyis auth <login|status|logout> [options]`
* **Purpose**: Manages GitHub organization credentials for centralized telemetry hub access.
* **Subcommands**:
  - `login [--token <tok>] [--gh] [-w|--workspace] [-e|--endpoint <url>] [--json]`: Authenticates user. `--gh` automatically lifts token from `gh auth token`.
  - `status [--json]`: Displays active authenticated user, GitHub organization, and endpoint URL.
  - `logout [--json]`: Clears credentials stored in `~/.config/agyis/credentials.json` (`0o600`).

### 11. `sync`
* **Syntax**: `agyis sync [options]`
* **Purpose**: Synchronizes local telemetry database with central gateway.
* **Modes**:
  - Default: Bi-directional synchronization (pulls remote updates, pushes local un-synced sessions).
  - `--push`: Pushes local un-synced sessions in client-side batches (10 sessions / 2,500 steps) to prevent HTTP 413.
  - `--pull`: Pulls remote deltas; enforces anti-echo filtering (`origin_developer != requesting_user`).
  - `--watch [--interval 5.0]`: Runs continuous background synchronization loop.
  - `--systemd`: Emits systemd user service unit definition.
  - `--service {install,status,start,stop,uninstall}`: Manages native background synchronization systemd user service.
  - `--interactive`, `--review`, `--dry-run`, `--all-developers`, `--developer <name>`, `--since <timestamp>`.

### 12. `init`
* **Syntax**: `agyis init [path] [-s|--stack <stk>] [--skills <list>] [--agents [list]] [--override] [--no-dedup] [-y|--yes] [--json]`
* **Purpose**: Initializes a project workspace with stack-tailored skills, tagged rules (`<!-- Added by AGYIS-HARNESS -->`), and optional subagents. Preserves existing domain rules in `AGENTS.md` and detects legacy `.agent/` configurations.
* **Flags & Options**:
  - `path`: Target workspace directory (defaults to current directory).
  - `-s`, `--stack <stk>`: Stack preset (`typescript`, `python`, `systems`, `shell`, `audit`). Auto-detects if omitted.
  - `--skills <list>`: Comma-separated list of modular skills to install to `<ws>/.agents/skills/`.
  - `--agents [list]`: Installs specialist agent definitions into `<ws>/.agents/agents/`.
  - `--override`: Force overwrite existing files even if different.
  - `--no-dedup`: Disables content-hash deduplication.
  - `-y`, `--yes`: Non-interactive mode, applies defaults.
  - `--json`: Emits workspace initialization report in JSON.

### 13. `harmonize`
* **Syntax**: `agyis harmonize [path] [--dry-run] [--json]`
* **Purpose**: Harmonizes legacy `.agent/` directories and PSL-HARNESS tagged rules into the modern `.agents/` structure and AGYIS-HARNESS demarcation fences non-destructively.
* **Flags & Options**:
  - `path`: Target workspace directory (defaults to current directory).
  - `--dry-run`: Validates migrations without mutating files on disk.
  - `--json`: Emits harmonization audit report in structured JSON format.

### 14. `onboard`
* **Syntax**: `agyis onboard [path] [flags]`
* **Purpose**: Turnkey brownfield workspace onboarding combining git topology probing, legacy `.agent/` archiving and deterministic 2-step pruning, decoupled language & architectural role presets, explicit skills provisioning, cache purging, git exclusion configuration, and pull request creation.
* **Flags**:
  - `path`: Target workspace path (defaults to current directory).
  - `--lang`, `--stack`, `-s`: Language preset (`typescript`, `node`, `javascript`, `python`, `rust`, `go`, `systems`, `shell`, `auto`).
  - `--role`, `-r`: Architectural role preset (`backend`, `frontend`, `fullstack`, `cli`, `library`, `mobile`, `desktop_gui`, `media`, `audio`, `infra`).
  - `--skills`: Comma-separated list of explicit skills to provision (overrides preset inference).
  - `--subproject`: Scoped subproject relative path for monorepos (e.g. `services/billing`).
  - `--create-branch [name]`: Dedicated onboarding branch isolation (defaults to `chore/agyis-harness-onboarding`).
  - `--allow-dirty`: Proceed on a dirty tree by automatically exporting `.agents/artifacts/wip-safety-pre-onboard.patch`.
  - `--purge-caches`: Purge build caches (`.next`, `.turbo`) before verification (default: True).
  - `--no-cache-purge`: Disable automatic build cache purging.
  - `--prune-legacy`: Safely archive legacy `.agent/` to tar.gz and prune (default: True).
  - `--no-prune`: Retain legacy `.agent/` directory on disk.
  - `--pr`, `--open-pr`: Open GitHub Pull Request via `gh pr create` upon verified test pass.
  - `--dry-run`: Preview all onboarding operations without filesystem or git mutations.
  - `--json`: Output machine-readable structured JSON report.
  - `--experimental-rea`: Provision Reverse Engineer Anything cleanroom specifications and ledgers.
* **Exit Codes**: `0` on success; `1` on dirty tree without `--allow-dirty`, invalid git repository, or missing path.

### 15. `install`
* **Syntax**: `agyis install [-g|--global] [--bin-dir <path>] [--symlink|--copy] [--dry-run] [--all-surfaces] [-w|--workspace [path]]`
* **Purpose**: Installs `agyis-harness` globally into Antigravity extension surfaces (`~/.gemini/config/plugins/agyis-harness/`) and deploys standalone executable (`~/.local/bin/agyis` and backward-compatible alias `~/.local/bin/psl`), OR initializes a project workspace when `-w`/`--workspace` is provided.
* **Flags**:
  - `-g`, `--global`: Installs standalone launcher scripts into user binary path (`~/.local/bin/agyis` and `~/.local/bin/psl`, `0o755`).
  - `--symlink`: Installs plugin via symlink (default; tracks development changes).
  - `--copy`: Installs plugin via hermetic file copy, enforcing ADR-014 packaging filters.
  - `--dry-run`: Validates path safety guards and prints planned actions without mutating disk.
  - `--all-surfaces`: Synchronizes all auxiliary Antigravity surface configurations.
  - `-w`, `--workspace [path]`: Routes to workspace initialization (`agyis init`), deploying stack skills and tagged rules.
  - `--stack`, `--skills`, `--agents`, `--override`, `--no-dedup`: Forwarded to workspace initialization engine.

### 16. `uninstall`
* **Syntax**: `agyis uninstall [--bin-dir <path>] [--dry-run] [--target <path>] [--json]`
* **Purpose**: Unlinks or removes installed plugin and standalone launcher script cleanly, enforcing path safety guards to guarantee `REPO_ROOT` is never touched.

### 17. `verify`
* **Syntax**: `agyis verify [--spec] [--workspace <path>] [--json]`
* **Purpose**: Cleanroom specification and reconstruction verification engine (ADR-028).
* **Flags**:
  - `--spec`: Verifies cleanroom specifications in `docs/specs/**`. Asserts zero executable code files exist inside specification directories and resets `spec_dirty = False` in the completion fence.
  - Without `--spec`: Delegates to `rea verify-reconstruction` to verify typed obligations in `.agents/ledger/manifest.json`.
  - `--workspace`, `-w`: Target workspace root path (default: current directory).
  - `--json`: Structured JSON verification output.
* **Exit Codes**: `0` on satisfied specifications/manifests; `1` if executable code exists in `docs/specs/` or if obligations remain unsatisfied.

### 18. `gui`
* **Syntax**: `agyis gui [--devtools] [--trajectory-debug] [--toggle] [--no-popup] [--wait <sec>] [--port-file <path>] [--json]`
* **Purpose**: Introspect and control Google Antigravity's Electron GUI via Chromium DevTools Protocol (CDP) WebSocket (ADR-014 / REA-SPEC-001).
* **Flags**:
  - `--trajectory-debug`: Injects developer flags into `localStorage` and opens Trajectory Debug View (`?trajectoryDebugOpen=true`) (default action).
  - `--no-popup`, `--setup-only`: Injects flags and hotkeys (F12, Ctrl+Shift+T) without opening the modal popup.
  - `--toggle`: Toggles Trajectory Debug View open/closed state.
  - `--devtools`: Inspects active port and prints Chrome Inspect and direct webview URLs.
  - `--wait <sec>`: Poll timeout for active Antigravity webview to become ready.
  - `--json`: Structured JSON connection and injection report.
* **Exit Codes**: `0` on successful injection; `1` if Antigravity GUI is not running or CDP fails.

---

### 19. `rules`
* **Syntax**: `agyis rules [--lint] [--dedup] [--workspace <path>]`
* **Purpose**: Audits, deduplicates, and harmonizes agent rule files across global and workspace configurations (Phase 21).
* **Flags**:
  - `--lint`: Lints rule files for formatting, duplicate invariant blocks, and outdated headers.
  - `--dedup`: Harmonizes duplicate rule declarations to eliminate redundant prompt context.

### 20. `release-notes`
* **Syntax**: `agyis release-notes [--base <commit>] [--tag <tag>] [--output <file>] [--gh-release <tag>]`
* **Purpose**: Automated conventional commit parser and publication-grade release notes generator (Phase 15).
* **Flags**:
  - `--base`: Base git commit or ref.
  - `--tag`: Target release tag.
  - `--output`: File path to output generated markdown release notes.
  - `--gh-release`: Update existing GitHub release via `gh release edit`.

### 21. `changelog` (Alias: `changelogs`)
* **Syntax**: `agyis changelog [--tag <ver>] [--base <ref>] [--rev <ref>] [--date <YYYY-MM-DD>] [--file <path>] [--write] [--backfill] [--style {canonical,keepachangelog}] [--workspace <path>] [--repo-url <url>] [--json]`
* **Purpose**: Native Keep-a-Changelog generator and idempotent `CHANGELOG.md` manager.

### 22. `checkpoint`
* **Syntax**: `agyis checkpoint {status,generate,create,verify,prune} [flags]`
* **Purpose**: Carrier-grade pre-compaction state capture, active plan synchronization, and session succession (ADR-031A, ADR-033).
* **Subcommands**:
  - `status`: Displays current checkpoint state and age.
  - `generate`: Generates `.agents/artifacts/cockpit_checkpoint.md` from live workspace state.
  - `create`: Creates an explicit manual checkpoint snapshot.
  - `verify`: Verifies checkpoint integrity and file hashes.
  - `prune`: Prunes stale checkpoints older than retention window.

### 23. `cockpit`
* **Syntax**: `agyis cockpit {status,route,verify} [flags]`
* **Purpose**: Standardized Cockpit Flight Director pairing dashboard and operational air traffic control (ADR-031A).
* **Subcommands**:
  - `status`: Flight deck health overview, token consumption gauges, active subagent registry, and git status.
  - `route <A-L|alias>`: Outputs structured dispatch briefing and transition payload for the 12 canonical routing workflows.
  - `verify`: Audits the active pairing session against the 5 flight director invariants.

### 24. `router` (Alias: `ladder`)
* **Syntax**: `agyis router [workflow] [--task-id <id>]` / `agyis ladder [workflow]`
* **Purpose**: Dynamic subagent router and execution pipeline dispatching specialized agent ladders (`Investigator -> Planner -> Builder -> Reviewer -> Custodian -> Auditor`).

### 25. `clean`
* **Syntax**: `agyis clean [--all] [--checkpoints] [--worktrees] [--dist]`
* **Purpose**: Multi-branch workspace hygiene, orphaned git worktree pruning, checkpoint cleanup, and build artifact removal (ADR-031A, ADR-031B).
* **Flags**:
  - `--all`: Purges all stale checkpoints, dead worktrees, and scratchpads.
  - `--worktrees`: Forces removal of orphaned subagent worktrees.
  - `--checkpoints`: Cleans expired checkpoint snapshots.
  - `--dist`: Removes distribution and build outputs.

### 26. `re`
* **Syntax**: `agyis re {status,init,patch-rea,pre-analyze,find,decompile,pcap,disasm,xrefs} [args]`
* **Purpose**: Cleanroom reverse engineering toolsuite and Ghidra acceleration engine (ADR-028, ADR-034, PSL-INV-009).
* **Subcommands**:
  - `status`: Reports status of dirtyroom scaffolding, symbol database, and REA patches.
  - `init`: Turnkey dirtyroom scaffolding (`.dirtyroom/{ghidra,symbols,logs,pcaps}`).
  - `patch-rea`: Idempotently patches `rea-agents` launcher for sub-2s decompilation on $>10\text{MB}$ binaries (`-noanalysis -readOnly`).
  - `pre-analyze <bin>`: Executes headless Ghidra pre-analysis and indexes symbols into SQLite.
  - `find <symbol>`: Sub-millisecond symbol and string query from pre-analyzed SQLite database.
  - `decompile <func>`: Targeted procedure decompilation using pre-analyzed Ghidra project.
  - `pcap <file>`: Inspects network packet captures.
  - `disasm <target>`: Disassembles instructions at a virtual address or function name via native `objdump` (`--binary`, `--bytes`, `--limit`).
  - `xrefs <target>`: Finds cross-references to a hexadecimal virtual address (`0x...`, `--binary`).

### 27. `ext`
* **Syntax**: `agyis ext {list,run,init} [args]`
* **Purpose**: Extensible workspace CLI command runner and management suite (ADR-034).
* **Subcommands**:
  - `list`: Lists discovered custom commands in `.agents/commands/` and `.agents/commands.json`.
  - `run <cmd> [args]`: Executes a workspace extension command with runtime injection.
  - `init <name>`: Scaffolds a new workspace extension template.

---

## 3. Verification & Compliance
To verify the CLI palette programmatically:

```bash
# Verify all 27 commands are registered and discoverable:
agyis --help
# or: python3 -m harness.cli --help

# Verify individual subcommand help dispatch:
for cmd in doctor hook test audit rules skills agents subagents status remote auth sync init harmonize onboard install uninstall verify gui release-notes changelog checkpoint cockpit router clean re ext; do
    agyis "$cmd" --help > /dev/null
done
```
