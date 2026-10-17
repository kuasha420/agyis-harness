<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Agyis Harness v1.0.0-rc5: Master GitHub Issues Staging Manifest

```
Document Reference : PSL-MANIFEST-2026-RC5-001
Status             : Official Publication-Grade Staging Manifest
Milestone          : v1.0.0-rc5 (Milestone ID: 1, Node: MI_kwDOU4VZGs4BHLW9)
Target Repository  : kuasha420/agyis-harness
Author             : Issue Creator Worker (worker_m2_issue_creator)
Orchestrator       : orchestrator_23 (ce0ce8ab-7285-4ded-926b-b7ea3aa34408)
Date               : 2026-10-17T05:33:00Z
Integrity Mode     : genuine
```

---

## 1. Executive Summary

This master staging manifest records the official, publication-grade GitHub issues published on **`kuasha420/agyis-harness`** to stage the core release requirements for **Agyis Harness `v1.0.0-rc5`**.

All 6 issues were mined from:
1. The **18-repository fleet audit** across `purrfectsoft`, `sakibtamim`, and `kuasha420` (`gap_cross_verification_report.md`).
2. The live rehydration and rebasing of **16 open PRs** across the 5 highest-velocity codebases (`docs/specs/rc4_rehydration_findings.md`).
3. The 1,247-line forensic gaps specification (`docs/specs/agyis-installation-harmonization-gaps.md`).
4. Out-of-band issue reports and cross-repository synchronization tickets (`Issue #57`).

Each issue has been created with:
- Full Context & Architectural Rationale grounded in empirical telemetry.
- Concrete Problem Statements.
- Exact line-level Code Targets in `harness/` and `tests/`.
- Implementation Proposals & System Architecture.
- Checkable Acceptance Criteria (`- [ ]`).
- Formal GitHub Labels (`rc5-blocker`, `p0`/`p1`, `cli`, `delivery`, `skills`, `telemetry`, `db-ops`, `docker`).
- Direct assignment to Milestone **`v1.0.0-rc5`**.

---

## 2. Master Issue Matrix

| Issue # | Issue Title | URL | Priority / Type | Labels | Milestone | Status |
| :---: | :--- | :--- | :---: | :--- | :---: | :---: |
| **#58** | **feat(cli): Unified 'agyis onboard' CLI Engine: Consolidated Topology, Preset Decoupling, Explicit Skills, Branch Isolation, and Single-Source Deduplication** | [kuasha420/agyis-harness#58](https://github.com/kuasha420/agyis-harness/issues/58) | P0 / Enhancement | `enhancement`, `p0`, `rc5-blocker`, `cli`, `delivery`, `skills` | `v1.0.0-rc5` | OPEN |
| **#59** | **feat(delivery): automated '.agents/archive/' safety backup lifecycle and deterministic legacy pruning** | [kuasha420/agyis-harness#59](https://github.com/kuasha420/agyis-harness/issues/59) | P0 / Enhancement | `enhancement`, `p0`, `rc5-blocker`, `delivery`, `cli` | `v1.0.0-rc5` | OPEN |
| **#60** | **fix(delivery): python test command extraction fallback for non-pyproject repositories (GAP-07)** | [kuasha420/agyis-harness#60](https://github.com/kuasha420/agyis-harness/issues/60) | P0 / Bug | `bug`, `p0`, `rc5-blocker`, `delivery` | `v1.0.0-rc5` | OPEN |
| **#61** | **feat(telemetry): native background sync service management via 'agyis sync --service' (#57)** | [kuasha420/agyis-harness#61](https://github.com/kuasha420/agyis-harness/issues/61) | P1 / Enhancement | `enhancement`, `p1`, `rc5-blocker`, `cli`, `telemetry`, `delivery` | `v1.0.0-rc5` | OPEN |
| **#62** | **feat(skills): dynamic database port collision detection and .env re-binding in db-ops** | [kuasha420/agyis-harness#62](https://github.com/kuasha420/agyis-harness/issues/62) | P1 / Enhancement | `enhancement`, `p1`, `rc5-blocker`, `skills`, `db-ops`, `docker` | `v1.0.0-rc5` | OPEN |
| **#63** | **feat(delivery): Automated Cache Invalidation in Rebase & Onboard Workflows: Pre-Verification Purging of '.next/' and '.turbo/' Build Artifacts** | [kuasha420/agyis-harness#63](https://github.com/kuasha420/agyis-harness/issues/63) | P1 / Enhancement | `enhancement`, `p1`, `rc5-blocker`, `delivery`, `cli` | `v1.0.0-rc5` | OPEN |
| *(Ref)* **#57** | *feat(telemetry): add canonical 'agyis sync --service' lifecycle management command* | [kuasha420/agyis-harness#57](https://github.com/kuasha420/agyis-harness/issues/57) | P1 / Enhancement | *(Original tracking stub)* | `v1.0.0-rc5` | OPEN |

---

## 3. Detailed Issue Specifications & Code Targets

### Issue #58: Unified 'agyis onboard' CLI Engine

- **Title**: `feat(cli): Unified 'agyis onboard' CLI Engine: Consolidated Topology, Preset Decoupling, Explicit Skills, Branch Isolation, and Single-Source Deduplication`
- **URL**: https://github.com/kuasha420/agyis-harness/issues/58
- **Classification**: P0 Blocker / Core Feature (`enhancement`, `p0`, `rc5-blocker`, `cli`, `delivery`, `skills`)
- **Origin**: GAP-04, GAP-10A / Rehydration Findings §3.1, §3.3, §3.4, §3.8

#### Architectural Rationale
Tooling fragmentation during initial onboarding required manually orchestrating `agyis harmonize`, `agyis init`, and `agyis install -w`. Lack of branch isolation tripped Husky branch-name hooks on `develop` (`psl-website` PR #61). Residual skill conflation left backend database skills in frontend codebases (`psl-boilerplate`, `psl-scaffold`, `chronicle-time-keeper`, `purrfect-download-manager`, `jimha`). Un-deduplicated workspace skills bloated prompt contexts by ~4,500 redundant tokens per turn.

#### Exact Code Targets in `harness/`
1. **`harness/cli.py:375-443` (`p_onboard` subparser)**:
   - Add `--skills` argument (`type=str, default=None`).
   - Change `--prune-legacy` to default to `True`.
   - Add `--no-prune` argument (`dest="prune_legacy", action="store_false"`).
   - Add `--create-branch` argument (default `None`, const `"chore/agyis-harness-onboarding"`).
   - Add `--allow-dirty` argument (`action="store_true", default=False`).
   - Add `--purge-caches` / `--no-cache-purge` argument (default `True`).
2. **`harness/commands/onboard.py:42-74` (`cmd_onboard`)**:
   - Signature expansion to accept `skills`, `create_branch`, `allow_dirty`, `prune_legacy`, `purge_caches`.
3. **`harness/commands/onboard.py:86-99` (Dirty Tree Safety)**:
   - Check `topology.is_dirty`. Abort if dirty and `--allow-dirty` is not passed; export `.agents/artifacts/wip-safety-pre-onboard.patch` if allowed.
4. **`harness/commands/onboard.py:100-128` (Branch Isolation)**:
   - Checkout dedicated onboarding branch before file writes.
5. **`harness/commands/onboard.py:166-199` (Skills Resolution & Deduplication)**:
   - Parse `--skills`, merge with presets, and invoke `enforce_single_source_skills(ws)` unconditionally.
6. **`tests/test_onboard.py:1-231`**:
   - Comprehensive test suite for all onboarding flags and isolation behaviors.

#### Acceptance Criteria
- [ ] `agyis onboard` CLI parser accepts `--skills`, `--subproject`, `--allow-dirty`, `--create-branch`, `--prune-legacy`, `--no-prune`, `--purge-caches`, and `--no-cache-purge`.
- [ ] Passing `--skills "storage-ops,sec-forensics"` resolves and installs the specified skills into `<workspace>/.agents/skills/`.
- [ ] `--prune-legacy` defaults to `True`; running `agyis onboard` on a repository with `.agent/` deterministically archives to `.agents/archive/` and prunes `.agent/` without requiring an explicit flag.
- [ ] Passing `--no-prune` preserves the legacy `.agent/` directory on disk and in git.
- [ ] When a repository working tree is dirty (`topology.is_dirty == True`) and `--allow-dirty` is omitted, `agyis onboard` aborts with exit code 1 and prints an actionable error message.
- [ ] When `--allow-dirty` is provided, onboarding proceeds and records a pre-onboard safety patch in `.agents/artifacts/wip-safety-pre-onboard.patch`.
- [ ] When `--create-branch` is specified, the engine creates and checks out the onboarding branch before modifying files or pushing.
- [ ] `enforce_single_source_skills()` runs during onboarding, removing workspace skill duplicates that shadow global plugins and reporting pruned skills in JSON output.
- [ ] Hermetic unit tests in `tests/test_onboard.py` cover all new flags and pass cleanly in `<1.0s`.
- [ ] Complete test suite (`./agyis test`) passes with 100% green exit code 0.

---

### Issue #59: Automated '.agents/archive/' Safety Backup Lifecycle

- **Title**: `feat(delivery): automated '.agents/archive/' safety backup lifecycle and deterministic legacy pruning`
- **URL**: https://github.com/kuasha420/agyis-harness/issues/59
- **Classification**: P0 Blocker / Core Feature (`enhancement`, `p0`, `rc5-blocker`, `delivery`, `cli`)
- **Origin**: GAP-01 / Rehydration Findings §3.2, §3.8, §4.1

#### Architectural Rationale
Passive copy migration left `.agent/` on disk, causing all 8 standard harmonized repositories to fail Tier 1 cleanliness tests (`verify_fleet.py:595-614`). Ad-hoc pruning with `git rm -rf .agent` left untracked local debris behind, while running `shutil.rmtree` without pre-prune archival risked irreversible work loss. Furthermore, creating backup archives in `.agents/archive/` without `.git/info/exclude` staged multi-megabyte binary `.tar.gz` blobs into git.

#### Exact Code Targets in `harness/`
1. **`harness/delivery/harmonize.py:235-256`**:
   - Pre-flight SHA-256 calculation for all files in `legacy_agent_dir`.
2. **`harness/delivery/harmonize.py:522-574` (Phase 3: Safety Archival)**:
   - Compressed archive creation (`legacy-agent-backup-<timestamp>.tar.gz`) and JSON manifest generation (`legacy-agent-backup-<timestamp>-manifest.json`).
3. **`harness/delivery/harmonize.py:576-628` (Phase 4: Deterministic Pruning)**:
   - 2-step removal (`git rm -rf .agent` + `shutil.rmtree`) and post-condition `assert not legacy_agent_dir.exists()`.
4. **`harness/delivery/constants.py:49-58` & `harness/delivery/git_hygiene.py:27-90`**:
   - Exclude `.agents/archive/` in `GIT_EXCLUDE_PATTERNS` written to `.git/info/exclude`.
5. **`harness/cli.py:365-369, 416-419`**:
   - Align `--prune-legacy` and `--backup` flags.
6. **`harness/delivery/workspace.py:488-497`**:
   - Modernize legacy notice string.

#### Acceptance Criteria
- [ ] `harmonize_workspace(ws, prune_legacy=True, backup=True)` creates a `.tar.gz` archive in `.agents/archive/` containing all pre-existing `.agent/` files with matching SHA-256 digests.
- [ ] A corresponding `-manifest.json` file is written alongside the tarball containing timestamps, file sizes, relative paths, SHA-256 digests, and any untracked debris files swept.
- [ ] In Git repositories, `configure_git_exclude(ws)` is automatically executed before archival, appending `.agents/archive/` to `.git/info/exclude` if not already present.
- [ ] Running `git status --porcelain` after onboarding confirms `.agents/archive/` is never staged as an untracked or modified file.
- [ ] Deterministic 2-step pruning successfully invokes `git rm -rf .agent` for git-tracked files and `shutil.rmtree` for untracked debris, guaranteeing `(ws / ".agent").exists()` is `False`.
- [ ] `assert not legacy_agent_dir.exists()` is executed as a hard invariant post-condition when `prune_legacy=True`.
- [ ] `--no-backup` flag disables tarball and manifest creation while safely pruning legacy files when explicitly commanded.
- [ ] `--backup-dir` / `--archive-dir` permits routing backups to an external directory outside the workspace.
- [ ] `agyis onboard` defaults `--prune-legacy` to `True`, with `--no-prune` providing explicit non-destructive retention.
- [ ] Dry-run mode (`--dry-run`) previews planned archival paths, manifest entries, and untracked file pruning with zero filesystem mutation.
- [ ] `harness/delivery/workspace.py` legacy notice is updated to cite `agyis harmonize` and `agyis onboard` instead of `/psl-harmonize`.
- [ ] Hermetic unit tests in `tests/test_harmonize.py` and `tests/test_onboard.py` verify all pruning, archival, manifest, and exclusion paths in <1.0s.

---

### Issue #60: Python Test Command Extraction Fallback (GAP-07)

- **Title**: `fix(delivery): python test command extraction fallback for non-pyproject repositories (GAP-07)`
- **URL**: https://github.com/kuasha420/agyis-harness/issues/60
- **Classification**: P0 Blocker / Defect (`bug`, `p0`, `rc5-blocker`, `delivery`)
- **Origin**: GAP-07 / Rehydration Findings §3.5

#### Architectural Rationale
Python command extraction was gated on `if pyproj.is_file():` (`harness/delivery/workspace.py:138`). In projects structured with `setup.py`, `setup.cfg`, `requirements.txt`, or standard `tests/` without `pyproject.toml` (e.g. `jimha` PR #1, `knot-mesh` PR #80, `purr` PR #14), extraction was completely skipped. This generated an empty Section 1 ("Project Command Dictionary") in `AGENTS.md`, breaking the Victory Pattern and causing Dynamic Repository Awareness (DRA) verification gate stalls.

#### Exact Code Targets in `harness/`
1. **`harness/delivery/workspace.py:137-188`**:
   - Replace `if pyproj.is_file():` with multi-manifest detection `is_python`.
   - Inspect `setup.py`, `setup.cfg`, `requirements.txt`, `Pipfile`, `poetry.lock`, `uv.lock`, and `tests/` / `test/`.
   - Resolve package manager execution prefix (`poetry run `, `uv run `, `pipenv run `).
   - Resolve test runner hierarchy (`pytest` if configured; fallback to `python3 -m unittest discover -s tests -v` or `-s test -v`).
   - Extract linters (`ruff`, `flake8`), formatters (`ruff`, `black`), and typecheckers (`mypy`, `pyright`).
2. **`harness/delivery/harmonize.py:360-375`**:
   - Injection of command dictionary into `AGENTS.md`.
3. **`tests/test_harmonize.py:870-904` & `tests/test_delivery.py:952-967`**:
   - Tests for non-pyproject Python workspaces.

#### Acceptance Criteria
- [ ] In a workspace with only `setup.py` and `tests/test_basic.py` (no `pyproject.toml`), `extract_command_dictionary(ws)` returns `commands["test"] = "python3 -m unittest discover -s tests -v"`.
- [ ] In a workspace with only `requirements.txt` and `test/test_basic.py` (no `pyproject.toml`), `commands["test"] = "python3 -m unittest discover -s test -v"`.
- [ ] In a workspace with `setup.cfg` containing `[tool:pytest]` and `tests/`, `commands["test"] = "pytest"`.
- [ ] In a workspace with `pytest.ini` and `setup.py` (no `pyproject.toml`), `commands["test"] = "pytest"`.
- [ ] In a workspace with `requirements.txt` declaring `pytest>=8.0.0`, `commands["test"] = "pytest"`.
- [ ] In a workspace with `poetry.lock` and `tests/`, command is prefixed: `poetry run python3 -m unittest discover -s tests -v` (or `poetry run pytest`).
- [ ] In a workspace with `uv.lock` and `tests/`, command is prefixed: `uv run python3 -m unittest discover -s tests -v` (or `uv run pytest`).
- [ ] In a workspace with `Pipfile.lock` or `Pipfile`, command is prefixed: `pipenv run ...`.
- [ ] In a workspace with `ruff.toml` or `.ruff.toml` (no `pyproject.toml`), `commands["lint"] = "ruff check ."` and `commands["format"] = "ruff format ."`.
- [ ] In a workspace with `mypy.ini` (no `pyproject.toml`), `commands["check"] = "mypy ."`.
- [ ] Corrupted or malformed `pyproject.toml` files do not raise uncaught exceptions; extraction falls back to manifest files gracefully.
- [ ] Hermetic unit tests in `tests/test_harmonize.py` and `tests/test_delivery.py` pass with 100% assertion coverage in <1.0s.

---

### Issue #61: Native Background Sync Service Management (#57)

- **Title**: `feat(telemetry): native background sync service management via 'agyis sync --service' (#57)`
- **URL**: https://github.com/kuasha420/agyis-harness/issues/61
- **Classification**: P1 Blocker / Enhancement (`enhancement`, `p1`, `rc5-blocker`, `cli`, `telemetry`, `delivery`)
- **Origin**: Issue #57 / GAP-05 / Rehydration Findings §4.3

#### Architectural Rationale
Continuous background telemetry synchronization across nodes and the central hub is vital for loop detection and transcript replication. Configuring the service currently requires manual shell redirection and terminal plumbing (`./agyis sync --systemd > ~/.config/systemd/user/agyis-sync.service`), which is error-prone, risks terminal hangs, and leaves orphan services upon teardown.

#### Exact Code Targets in `harness/`
1. **`harness/cli.py:285-303`**:
   - Register `--service {install,status,start,stop,restart,uninstall}` on `p_sync`.
2. **`harness/commands/sync.py:18-41`**:
   - Route `--service` to `service.handle_service_command(args)`.
3. **`harness/telemetry/sync/service.py` (New module)**:
   - Implement `install_sync_service`, `get_sync_service_status`, `manage_sync_service`.
4. **`harness/telemetry/sync/systemd.py:17-42`**:
   - Update unit header description and add optional `endpoint` parameter.
5. **`harness/skills/telemetry-sync/SKILL.md:71-86` & `docs/runbooks/telemetry-sync.md:92-107`**:
   - Document canonical CLI service commands.
6. **`tests/test_sync_service.py` & `tests/test_cli.py:528-536`**:
   - Unit tests for service lifecycle with mocked subprocess calls.

#### Acceptance Criteria
- [ ] `harness/cli.py` registers `--service` on `p_sync` accepting `install`, `status`, `start`, `stop`, `restart`, `uninstall`.
- [ ] `agyis sync --service install` creates `~/.config/systemd/user/agyis-sync.service` with valid unit syntax using active `sys.executable`.
- [ ] `install` executes `systemctl --user daemon-reload`, `enable`, and `start` cleanly.
- [ ] `agyis sync --service status` returns exit code 0 when service is active and formats output without launching interactive pagers.
- [ ] `agyis sync --service status --json` emits valid JSON with `installed`, `active`, `enabled`, `substate`, and `pid`.
- [ ] `agyis sync --service stop` and `start` correctly alter unit execution state.
- [ ] `agyis sync --service restart` triggers clean unit reload.
- [ ] `agyis sync --service uninstall` disables unit, deletes unit file, executes `daemon-reload`, and exits 0 idempotently.
- [ ] Graceful non-systemd fallback: returns non-zero exit with clear guidance to run `agyis sync --watch` when `systemctl` is unavailable.
- [ ] `harness/skills/telemetry-sync/SKILL.md` and `docs/runbooks/telemetry-sync.md` updated to feature `agyis sync --service`.
- [ ] Hermetic unit test suite (`tests/test_sync_service.py`) passes in `<0.5s` with mocked subprocess execution.
- [ ] Full harness test suite passes: `python3 -m harness.cli test` (847+ tests green in `<15s`).

---

### Issue #62: Dynamic Database Port Collision Detection in db-ops

- **Title**: `feat(skills): dynamic database port collision detection and .env re-binding in db-ops`
- **URL**: https://github.com/kuasha420/agyis-harness/issues/62
- **Classification**: P1 Blocker / Enhancement (`enhancement`, `p1`, `rc5-blocker`, `skills`, `db-ops`, `docker`)
- **Origin**: Rehydration Findings §3.2, §4.4

#### Architectural Rationale
In `purrfectsoft/mm-website`, `pnpm build` unexpectedly failed during Next.js static prerendering with Prisma `P1000: Authentication failed against database server`. A PostgreSQL container from an entirely different repository (`jasper_dev_postgres`) was occupying host port 5432. The agent misdiagnosed the failure as bad credentials rather than port collision. The `db-ops` skill lacks host collision inspection and automated free port reallocation.

#### Exact Code Targets in `harness/`
1. **`harness/skills/db-ops/SKILL.md` & `.agents/skills/db-ops/SKILL.md` (lines 147–172)**:
   - Add Section 4.4 (Host port 5432 collision probing), 4.5 (Dynamic port discovery & re-binding), 4.6 (`detect_port_collision.py`).
2. **`harness/skills/db-ops/scripts/detect_port_collision.py` (New standalone script)**:
   - Probing: Socket bind -> Docker ps publish check -> `ss`/`lsof` host process attribution.
   - Dynamic port scanning across 5432..5442.
   - Regex-safe `.env` `DATABASE_URL` and `POSTGRES_PORT` re-binding.
3. **`harness/runtime/hygiene_checks.py:31-36, 98-100`**:
   - `check_database_port_conflicts()` probe.
4. **`harness/runtime/doctor.py:96-105`**:
   - Wire port conflict diagnostics into `agyis doctor`.
5. **`harness/commands/onboard.py:140-200`**:
   - Run collision check during onboarding of backend/fullstack roles.
6. **`tests/test_db_ops_skill.py`**:
   - Unit tests for collision detection and surgical `.env` updating.

#### Acceptance Criteria
- [ ] `harness/skills/db-ops/SKILL.md` and `.agents/skills/db-ops/SKILL.md` updated with Sections 4.4, 4.5, and 4.6 covering port collision probing and dynamic re-binding.
- [ ] Standalone script `harness/skills/db-ops/scripts/detect_port_collision.py` implemented using Python standard library only.
- [ ] `detect_port_collision.py --check` accurately identifies whether port 5432 is free, self-owned, or collided with a foreign container.
- [ ] `detect_port_collision.py --find-free` scans ports 5432–5440 and returns the first unbound port.
- [ ] `detect_port_collision.py --rebind --env <path>` surgically updates `POSTGRES_PORT` and `DATABASE_URL` without corrupting surrounding variables or comments.
- [ ] `detect_port_collision.py --json` outputs structured schema (`status`, `port`, `owner`, `action_taken`).
- [ ] `check_database_port_conflicts()` added to `harness/runtime/hygiene_checks.py` and surfaced in `agyis doctor`.
- [ ] `agyis onboard` warns if target workspace has a colliding database port before running verification gates.
- [ ] Comprehensive unit tests in `tests/test_db_ops_skill.py` pass cleanly in `<1.0s` with mocked socket and Docker calls.
- [ ] Full harness test suite passes: `python3 -m harness.cli test` (847+ tests green in `<15s`).

---

### Issue #63: Automated Cache Invalidation in Rebase & Onboard Workflows

- **Title**: `feat(delivery): Automated Cache Invalidation in Rebase & Onboard Workflows: Pre-Verification Purging of '.next/' and '.turbo/' Build Artifacts`
- **URL**: https://github.com/kuasha420/agyis-harness/issues/63
- **Classification**: P1 Blocker / Enhancement (`enhancement`, `p1`, `rc5-blocker`, `delivery`, `cli`)
- **Origin**: GAP-06 / Rehydration Findings §3.1, §4.2

#### Architectural Rationale
Next.js generates TypeScript declarations in `.next/types/app/**/*.ts`. Because `.next/` is gitignored, rebasing or switching branches leaves stale type definitions from previously active routes behind. Subsequent compilation commands (`tsc`, `turbo run typecheck`) fail with obscure `TS2307` errors for non-existent routes. Manually running `rm -rf .next .turbo` fixes the failure immediately. Automating cache invalidation is an essential onboarding and rebase prerequisite.

#### Exact Code Targets in `harness/`
1. **`harness/delivery/cache.py` (New module)**:
   - `purge_workspace_build_caches(workspace_dir, target_dirs, dry_run, max_depth=3)`.
   - Bounded traversal searching for `.next`, `.turbo`, `node_modules/.cache`.
   - Security containment assertion: `target.resolve().is_relative_to(ws.resolve())`.
   - Unlink symlinks directly without traversing external contents.
2. **`harness/delivery/__init__.py`**:
   - Export `purge_workspace_build_caches`.
3. **`harness/commands/onboard.py:130-146`**:
   - Integrate cache purge before verification; record `"purged_caches"` in JSON output.
4. **`harness/cli.py:375-443`**:
   - Add `--purge-caches` and `--no-cache-purge` on `p_onboard`.
5. **`tests/test_cache_invalidation.py`**:
   - Unit tests verifying boundary isolation, symlink safety, and monorepo recursion.

#### Acceptance Criteria
- [ ] Dedicated helper `purge_workspace_build_caches()` implemented in `harness/delivery/cache.py` using standard library only (`shutil`, `pathlib`, `os`).
- [ ] Targets `.next`, `.turbo`, and `node_modules/.cache` across root directory and subproject packages (`apps/*`, `packages/*`, `modules/*`) bounded to depth $\le 3$.
- [ ] Strict containment assertion prevents deleting any directory or target outside `workspace_dir.resolve()`.
- [ ] Symlinked cache directories are unlinked without recursively traversing or deleting external target contents.
- [ ] `dry_run=True` returns list of identified cache directories with zero filesystem modification.
- [ ] `agyis onboard` incorporates cache purging by default and exposes `--no-cache-purge` to bypass.
- [ ] JSON output of `agyis onboard` includes `"purged_caches": [ ... ]`.
- [ ] Hermetic unit tests in `tests/test_cache_invalidation.py` execute in `<0.2s` with 100% pass rate.
- [ ] Verification command `./agyis test` passes completely (exit code 0).

---

## 4. Verification Proofs of Issue Creation

### A. Milestone `v1.0.0-rc5` Issue Roster
```text
$ gh issue list --repo kuasha420/agyis-harness --milestone "v1.0.0-rc5"

ID   TITLE                                                                          LABELS                                            UPDATED
#63  feat(delivery): Automated Cache Invalidation in Rebase & Onboard Workflows...  enhancement, rc5-blocker, p1, delivery, cli       Just now
#62  feat(skills): dynamic database port collision detection and .env re-binding... enhancement, rc5-blocker, p1, skills, db-ops...   Just now
#61  feat(telemetry): native background sync service management via 'agyis sync...  enhancement, rc5-blocker, p1, cli, telemetry...   Just now
#60  fix(delivery): python test command extraction fallback for non-pyproject...    bug, rc5-blocker, p0, delivery                    Just now
#59  feat(delivery): automated '.agents/archive/' safety backup lifecycle and...   enhancement, rc5-blocker, p0, delivery, cli       Just now
#58  feat(cli): Unified 'agyis onboard' CLI Engine: Consolidated Topology...        enhancement, rc5-blocker, p0, cli, delivery...    Just now
#57  feat(telemetry): add canonical 'agyis sync --service' lifecycle management...  (Assigned to v1.0.0-rc5 milestone)                Just now
```

### B. Verification of Issue #58
```text
$ gh issue view 58 --repo kuasha420/agyis-harness --json number,title,state,milestone,labels
{
  "number": 58,
  "title": "feat(cli): Unified 'agyis onboard' CLI Engine: Consolidated Topology, Preset Decoupling, Explicit Skills, Branch Isolation, and Single-Source Deduplication",
  "state": "OPEN",
  "milestone": { "title": "v1.0.0-rc5" },
  "labels": [
    { "name": "cli" },
    { "name": "delivery" },
    { "name": "enhancement" },
    { "name": "p0" },
    { "name": "rc5-blocker" },
    { "name": "skills" }
  ]
}
```

### C. Verification of Issue #59
```text
$ gh issue view 59 --repo kuasha420/agyis-harness --json number,title,state,milestone,labels
{
  "number": 59,
  "title": "feat(delivery): automated '.agents/archive/' safety backup lifecycle and deterministic legacy pruning",
  "state": "OPEN",
  "milestone": { "title": "v1.0.0-rc5" },
  "labels": [
    { "name": "cli" },
    { "name": "delivery" },
    { "name": "enhancement" },
    { "name": "p0" },
    { "name": "rc5-blocker" }
  ]
}
```

### D. Verification of Issue #60
```text
$ gh issue view 60 --repo kuasha420/agyis-harness --json number,title,state,milestone,labels
{
  "number": 60,
  "title": "fix(delivery): python test command extraction fallback for non-pyproject repositories (GAP-07)",
  "state": "OPEN",
  "milestone": { "title": "v1.0.0-rc5" },
  "labels": [
    { "name": "bug" },
    { "name": "delivery" },
    { "name": "p0" },
    { "name": "rc5-blocker" }
  ]
}
```

### E. Verification of Issue #61
```text
$ gh issue view 61 --repo kuasha420/agyis-harness --json number,title,state,milestone,labels
{
  "number": 61,
  "title": "feat(telemetry): native background sync service management via 'agyis sync --service' (#57)",
  "state": "OPEN",
  "milestone": { "title": "v1.0.0-rc5" },
  "labels": [
    { "name": "cli" },
    { "name": "delivery" },
    { "name": "enhancement" },
    { "name": "p1" },
    { "name": "rc5-blocker" },
    { "name": "telemetry" }
  ]
}
```

### F. Verification of Issue #62
```text
$ gh issue view 62 --repo kuasha420/agyis-harness --json number,title,state,milestone,labels
{
  "number": 62,
  "title": "feat(skills): dynamic database port collision detection and .env re-binding in db-ops",
  "state": "OPEN",
  "milestone": { "title": "v1.0.0-rc5" },
  "labels": [
    { "name": "db-ops" },
    { "name": "docker" },
    { "name": "enhancement" },
    { "name": "p1" },
    { "name": "rc5-blocker" },
    { "name": "skills" }
  ]
}
```

### G. Verification of Issue #63
```text
$ gh issue view 63 --repo kuasha420/agyis-harness --json number,title,state,milestone,labels
{
  "number": 63,
  "title": "feat(delivery): Automated Cache Invalidation in Rebase & Onboard Workflows: Pre-Verification Purging of '.next/' and '.turbo/' Build Artifacts",
  "state": "OPEN",
  "milestone": { "title": "v1.0.0-rc5" },
  "labels": [
    { "name": "cli" },
    { "name": "delivery" },
    { "name": "enhancement" },
    { "name": "p1" },
    { "name": "rc5-blocker" }
  ]
}
```

---
*End of Master Issue Staging Manifest.*
