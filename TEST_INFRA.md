# TEST_INFRA.md — Agyis Harness v1.0.0 E2E Test Suite Infrastructure

## 1. Executive Summary & Verification Methodology
This document defines the opaque-box End-to-End (E2E) Test Suite architecture for the **Agyis Harness v1.0.0 Full-Surface Bug Bash**, focusing on **Quadrant 1 (Real-Project Onboarding & Harmonization)** and **Quadrant 4 (Live In-Situ HUD Dogfooding)** as specified in `PROJECT.md` and `ORIGINAL_REQUEST.md`.

All tests strictly adhere to the universal empirical agent invariants:
- **PSL-INV-001 (Universal Automated Verification Standard)**: Fast (<0.05s per unit, sub-second execution per module), hermetic, exit-code verified test execution with zero external network dependencies.
- **PSL-INV-007 (Clean-Room Verification Contract)**: Strict isolation using `tempfile.TemporaryDirectory()`, mocking external sockets/subprocesses, and asserting observable public CLI/API outputs.
- **PSL-INV-010 (Anti-Vibe-Coding & Dynamic Lifecycle)**: Multi-session dynamic traversal, route switching, and state invalidation verification.

---

## 2. Test Architecture & Runner Palette

### Execution Command
```bash
# Run the complete Bug Bash E2E Test Suite
python3 -m unittest tests/test_e2e_bugbash.py

# Run specific tier test classes
python3 -m unittest tests.test_e2e_bugbash.TestTier1FeatureCoverage
python3 -m unittest tests.test_e2e_bugbash.TestTier2BoundaryCases
python3 -m unittest tests.test_e2e_bugbash.TestTier3CrossFeatureInteractions
python3 -m unittest tests.test_e2e_bugbash.TestTier4RealWorldScenarios
```

### 4-Tier Summary Table
| Tier | Description | Requirement | Test Cases |
|------|-------------|-------------|------------|
| **Tier 1** | Feature Coverage | >=5 tests per feature (14 features) | 70 |
| **Tier 2** | Boundary & Corner Cases | >=5 tests per feature (14 features) | 70 |
| **Tier 3** | Cross-Feature Interactions | >=14 pairwise combinations | 14 |
| **Tier 4** | Real-World Scenarios | >=7 realistic application workloads | 7 |
| **Total** | Full Bug Bash Suite | Exhaustive opaque-box verification | **161** |

---

## 3. Tier 1: Feature Coverage (70 Test Cases)

### Feature 1: Harmonization Detection & Migration
- `test_t1_f01_01_detect_legacy_agent_dir`: Verifies detection of legacy `.agent/` directory with rules, agents, and workflows.
- `test_t1_f01_02_migrate_rules_to_agents_rules`: Asserts `.agent/rules/*.md` are migrated to `.agents/rules/*.md`.
- `test_t1_f01_03_convert_workflows_to_skills`: Asserts `.agent/workflows/*.md` are converted to `.agents/skills/<name>/SKILL.md` with synthesized YAML frontmatter.
- `test_t1_f01_04_rewrite_internal_agent_references`: Verifies that internal path references (`.agent/rules` -> `.agents/rules`) are rewritten in migrated files.
- `test_t1_f01_05_dry_run_zero_filesystem_mutations`: Asserts `--dry-run` reports planned migrations with exit code 0 and zero disk side effects.

### Feature 2: Harmonization Safety Archiving
- `test_t1_f02_01_backup_tarball_created`: Verifies `.agents/archive/legacy-agent-backup-<ts>.tar.gz` is created upon `--apply --backup`.
- `test_t1_f02_02_backup_manifest_json_created`: Verifies corresponding `.agents/archive/legacy-agent-backup-<ts>-manifest.json` contains SHA-256 digests.
- `test_t1_f02_03_backup_manifest_integrity`: Validates file counts, byte sizes, and timestamps in manifest match the archived tarball contents.
- `test_t1_f02_04_custom_archive_dir`: Asserts `--backup-dir <path>` redirects backup tarball and manifest to custom destination.
- `test_t1_f02_05_no_backup_flag_skips_archive`: Asserts `--no-backup` safely disables archive generation while completing migration.

### Feature 3: Harmonization Tagged Fences & Link Sanitizer
- `test_t1_f03_01_migrate_legacy_psl_tagged_fence`: Verifies `<!-- Added by PSL-HARNESS -->` is replaced with `<!-- Added by AGYIS-HARNESS -->`.
- `test_t1_f03_02_preserve_custom_user_rules`: Asserts user-defined rules outside the tagged fences in `AGENTS.md` remain 100% intact.
- `test_t1_f03_03_inject_command_dictionary`: Verifies Section 1 explicit command dictionary is extracted from project manifests and injected into the tagged fence.
- `test_t1_f03_04_sanitize_markdown_links`: Asserts relative links pointing to `.agent/...` across all workspace `.md` files are sanitized to `.agents/...`.
- `test_t1_f03_05_idempotent_tagged_fence_update`: Asserts running harmonize on an already up-to-date `AGENTS.md` results in `already_up_to_date` action.

### Feature 4: Onboarding Dirty Tree Guard
- `test_t1_f04_01_dirty_tree_aborts_without_allow_dirty`: Asserts `agyis onboard` halts with exit code 1 when uncommitted git changes exist.
- `test_t1_f04_02_dirty_tree_json_error_contract`: Verifies JSON output contains `{"success": false, "is_dirty": true}` when dirty tree rejected.
- `test_t1_f04_03_clean_tree_proceeds_without_allow_dirty`: Asserts clean repository working tree bypasses dirty tree guard smoothly.
- `test_t1_f04_04_allow_dirty_flag_permits_execution`: Asserts `--allow-dirty` allows onboarding to proceed despite uncommitted modifications.
- `test_t1_f04_05_untracked_files_dirty_evaluation`: Verifies dirty state correctly considers untracked files subject to git status rules.

### Feature 5: Onboarding Safety Patch Generation
- `test_t1_f05_01_pre_onboard_safety_patch_created`: Verifies `.agents/artifacts/pre_onboard_safety.patch` is generated when `--allow-dirty` is enabled.
- `test_t1_f05_02_safety_patch_contains_git_diff`: Asserts safety patch contains the exact unified diff of uncommitted changes (`git diff HEAD`).
- `test_t1_f05_03_backward_compatible_patch_symlink`: Asserts `wip-safety-pre-onboard.patch` is created as a symlink or alias to `pre_onboard_safety.patch`.
- `test_t1_f05_04_dry_run_safety_patch_omission`: Asserts `--dry-run` does not write safety patch to disk but reports planned patch path.
- `test_t1_f05_05_git_exclude_safety_patch`: Verifies `.agents/artifacts/` or safety patch files are added to `.git/info/exclude`.

### Feature 6: Onboarding Isolated Branch Creation
- `test_t1_f06_01_create_branch_flag_checks_out_new_branch`: Asserts `--create-branch <name>` creates and checks out dedicated branch.
- `test_t1_f06_02_default_branch_naming`: Asserts `--create-branch` without value defaults to `chore/agyis-harness-onboarding`.
- `test_t1_f06_03_existing_branch_checkout`: Asserts onboarding switches to existing target branch if it already exists.
- `test_t1_f06_04_purge_build_caches_on_branch`: Asserts stale build caches (`.next/`, `.turbo/`, `node_modules/.cache`) are purged on branch creation.
- `test_t1_f06_05_no_cache_purge_flag`: Asserts `--no-cache-purge` flag preserves existing build cache directories.

### Feature 7: Monorepo Subproject Targeting
- `test_t1_f07_01_subproject_path_resolution`: Asserts `--subproject <relpath>` resolves subproject workspace within root repository.
- `test_t1_f07_02_subproject_nonexistent_fails`: Asserts invalid subproject path halts with exit code 1 and error message.
- `test_t1_f07_03_subproject_scoped_skills`: Asserts provisioned skills are placed inside `<subproject>/.agents/skills/`.
- `test_t1_f07_04_subproject_git_root_preserved`: Asserts git operations (branch checkout, diff, status) execute against git root repository.
- `test_t1_f07_05_subproject_cache_purging`: Asserts cache purge scopes correctly to `<subproject>` build artifacts.

### Feature 8: Multi-Language DRA Test Harmonization
- `test_t1_f08_01_rust_cargo_test_audit`: Asserts `psl-test-harmonize` audits `Cargo.toml` and detects `cargo test` framework.
- `test_t1_f08_02_node_vitest_audit`: Asserts audit detects `vitest` in `package.json` with `pnpm`/`npm`/`bun` package manager.
- `test_t1_f08_03_generate_test_manifest_json`: Verifies `.agyis/test_manifest.json` is generated adhering to schema version 1.0.0.
- `test_t1_f08_04_inject_diff_test_scripts`: Asserts `test:diff`, `test:watch`, `test:affected`, and `test:full` scripts are planned for injection.
- `test_t1_f08_05_pre_mutation_backup_patch`: Asserts `.agyis/backups/test_harmonize_<ts>.patch` is created before modifying test manifests.

### Feature 9: Multi-Language DRA Idempotency
- `test_t1_f09_01_zero_mutations_on_pre_harmonized`: Asserts running test harmonization on already harmonized project yields 0 mutations.
- `test_t1_f09_02_manifest_retained_on_re_run`: Asserts `.agyis/test_manifest.json` is updated with fresh timestamp without altering script configs.
- `test_t1_f09_03_custom_scripts_preserved`: Asserts pre-existing custom test scripts (`test:e2e`, `test:coverage`) are never deleted or overridden.
- `test_t1_f09_04_backup_patch_omitted_when_zero_mutations`: Asserts backup patch is not generated when 0 file changes occur.
- `test_t1_f09_05_cli_exit_code_zero_idempotent`: Asserts `agyis harmonize test` exits with code 0 on idempotent execution.

### Feature 10: Dynamic SPA Route Switching
- `test_t1_f10_01_intercept_pushstate`: Verifies `history.pushState` and `history.replaceState` triggers `agyis:routechange` event.
- `test_t1_f10_02_extract_conversation_id_from_path`: Asserts `/c/:id` SPA route pathname correctly extracts conversation UUID.
- `test_t1_f10_03_route_change_updates_hud_context`: Asserts route change event triggers context reload in `window.__agyis_hud_load_convo`.
- `test_t1_f10_04_popstate_event_handling`: Asserts browser back/forward navigation (`popstate`) synchronizes active HUD context.
- `test_t1_f10_05_stale_dom_purged_on_route_switch`: Asserts `#agyis-trajectory-hud` stale state is invalidated upon switching conversations.

### Feature 11: Active Subagent Window Detection
- `test_t1_f11_01_subagent_tab_url_param_priority`: Asserts `?tab=subagent_convo__<uuid>` takes priority over `/c/:id` pathname route.
- `test_t1_f11_02_extract_subagent_uuid`: Asserts extractor strips `subagent_convo__` prefix and extracts pure subagent UUID.
- `test_t1_f11_03_render_subagent_badge`: Asserts HUD header renders `(subagent)` badge when active conversation is a subagent.
- `test_t1_f11_04_parent_pill_navigation`: Asserts `← Parent` pill is displayed and contains parent conversation link.
- `test_t1_f11_05_fallback_to_route_when_tab_absent`: Asserts URL fallback correctly resolves `/c/:id` when no subagent tab parameter exists.

### Feature 12: Live ConnectRPC 60 FPS Streaming
- `test_t1_f12_01_insitu_connect_client_init`: Asserts `InSituConnectClient` initializes with dynamic port, base URL, and CSRF token.
- `test_t1_f12_02_connectrpc_envelope_framing`: Verifies 5-byte Connect envelope framing (flags: uint8 + length: uint32be).
- `test_t1_f12_03_stream_render_coordinator_raf_batching`: Asserts incoming deltas are queued and flushed at 60 FPS via `requestAnimationFrame`.
- `test_t1_f12_04_csrf_token_header_injection`: Asserts `x-codeium-csrf-token` header is attached from `window.__APP_CONFIG__.csrfToken`.
- `test_t1_f12_05_stream_conversation_lifecycle_invocation`: Asserts `streamConversation` is invoked during HUD initialization for real-time telemetry.

### Feature 13: Live DevTools CDP Controller
- `test_t1_f13_01_read_devtools_active_port`: Asserts `get_devtools_active_port` reads port from `DevToolsActivePort` file.
- `test_t1_f13_02_discover_page_target`: Asserts `find_page_target` queries `http://127.0.0.1:<port>/json` and finds Antigravity webview.
- `test_t1_f13_03_cdp_evaluate_expression`: Asserts `CDPWebSocketClient.evaluate` sends `Runtime.evaluate` and parses result.
- `test_t1_f13_04_inject_trajectory_debug_flags`: Asserts developer flag overrides are written to localStorage.
- `test_t1_f13_05_hotkey_listener_installation`: Asserts F12 and Ctrl+Shift+T keydown listeners are injected cleanly.

### Feature 14: E2E Regression & Tier Verification
- `test_t1_f14_01_cli_version_flag`: Asserts `agyis --version` prints valid semantic version and exits 0.
- `test_t1_f14_02_cli_help_lists_all_subcommands`: Asserts `agyis --help` lists `harmonize`, `onboard`, `gui`, `test`, `doctor`.
- `test_t1_f14_03_psl_deprecation_warning_isolated_stderr`: Asserts legacy `psl` invocation outputs deprecation warning strictly to stderr.
- `test_t1_f14_04_pure_json_stdout_guarantee`: Asserts `--json` flag on CLI subcommands returns parseable JSON with 0 stdout noise.
- `test_t1_f14_05_exit_code_discipline`: Asserts CLI consistently returns 0 on success and 1 on error across all subcommands.

---

## 4. Tier 2: Boundary & Corner Cases (70 Test Cases)

### Feature 1 Boundaries: Harmonization Migration
- `test_t2_f01_01_empty_agent_dir`: Harmonization on `.agent/` containing only empty subdirectories succeeds with 0 migrated items.
- `test_t2_f01_02_broken_symlinks_in_agent_dir`: Symlinks pointing to non-existent targets are ignored without crashes.
- `test_t2_f01_03_unreadable_file_permissions`: Unreadable file in legacy rules returns clear error message and exit code 1.
- `test_t2_f01_04_deeply_nested_rule_directories`: Rules nested 5+ subdirectories deep maintain directory structure in `.agents/rules/`.
- `test_t2_f01_05_special_characters_in_filenames`: Filenames containing spaces, unicode, or hyphens migrate without corruption.

### Feature 2 Boundaries: Safety Archiving
- `test_t2_f02_01_empty_agent_dir_archived`: Empty `.agent/` archives valid tarball containing empty directory node.
- `test_t2_f02_02_archive_path_read_only`: Harmonization halts cleanly if archive directory has no write permissions.
- `test_t2_f02_03_existing_tarball_collision`: Timestamp collision handling ensures unique archive names.
- `test_t2_f02_04_zero_byte_files_in_manifest`: Zero-byte files have SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- `test_t2_f02_05_corrupted_existing_tarball`: Existing corrupted files in archive directory do not impede creating new backup.

### Feature 3 Boundaries: Tagged Fences & Link Sanitizer
- `test_t2_f03_01_malformed_unclosed_fence`: `AGENTS.md` with unclosed `<!-- Added by PSL-HARNESS -->` tags handles cleanly.
- `test_t2_f03_02_empty_agents_md`: Empty `AGENTS.md` injects tagged block as entire file content.
- `test_t2_f03_03_nonexistent_agents_md`: Missing `AGENTS.md` creates new file with tagged fence.
- `test_t2_f03_04_multiple_legacy_fences`: Multiple legacy fence blocks are consolidated or updated safely.
- `test_t2_f03_05_crlf_windows_newlines`: Windows `\r\n` line endings in `AGENTS.md` preserve normalized line endings.

### Feature 4 Boundaries: Dirty Tree Guard
- `test_t2_f04_01_staged_changes_only`: Only staged changes (`git add` but uncommitted) trigger dirty tree guard.
- `test_t2_f04_02_unstaged_modified_only`: Unstaged modifications to tracked files trigger dirty guard.
- `test_t2_f04_03_untracked_gitignored_files`: Ignored files in `.gitignore` do not trigger dirty guard.
- `test_t2_f04_04_deleted_tracked_files`: Deleted files (`git rm` or working tree removal) trigger dirty guard.
- `test_t2_f04_05_non_git_workspace`: Running onboard on non-git directory fails gracefully with git topology error.

### Feature 5 Boundaries: Safety Patch Generation
- `test_t2_f05_01_binary_file_diff_handling`: Uncommitted binary files generate git binary patch or diff cleanly.
- `test_t2_f05_02_massive_diff_generation`: Very large diff (>10,000 lines) writes completely without truncation.
- `test_t2_f05_03_staged_and_unstaged_diff_capture`: Safety patch includes both staged (`--cached`) and unstaged diffs.
- `test_t2_f05_04_patch_directory_permission_denied`: Read-only artifacts directory reports clean error.
- `test_t2_f05_05_consecutive_onboard_patch_overwrite`: Running onboard twice overwrites or updates safety patch safely.

### Feature 6 Boundaries: Isolated Branch Creation
- `test_t2_f06_01_invalid_branch_characters`: Branch names with invalid git characters (e.g., spaces, `~`, `^`, `:`) report error.
- `test_t2_f06_02_detached_head_state`: Creating branch from detached HEAD state checks out branch successfully.
- `test_t2_f06_03_branch_already_checked_out`: Specifying branch that is already active proceeds without checkout failure.
- `test_t2_f06_04_empty_cache_directories`: Purging non-existent or empty `.next/` and `.turbo/` proceeds without error.
- `test_t2_f06_05_deeply_nested_caches`: Subproject nested cache directories are pruned recursively.

### Feature 7 Boundaries: Monorepo Subproject Targeting
- `test_t2_f07_01_deeply_nested_subproject`: Subproject path `packages/core/submodule/app` resolves correctly.
- `test_t2_f07_02_subproject_with_trailing_slash`: `packages/react/` with trailing slash handles identically to without.
- `test_t2_f07_03_relative_dot_subproject`: `--subproject .` resolves to workspace root.
- `test_t2_f07_04_subproject_outside_repo`: `--subproject ../outside` path traversal halts with security/validation error.
- `test_t2_f07_05_symlinked_subproject`: Subproject directory that is a symlink resolves to its real canonical path.

### Feature 8 Boundaries: Multi-Language DRA Test Harmonization
- `test_t2_f08_01_corrupted_package_json`: Malformed JSON in `package.json` reports parse error without crashing.
- `test_t2_f08_02_missing_scripts_field`: `package.json` with no `"scripts"` key initializes `"scripts"` object and injects targets.
- `test_t2_f08_03_tauri_cargo_manifest`: Detection resolves `src-tauri/Cargo.toml` in hybrid desktop applications.
- `test_t2_f08_04_read_only_manifest_file`: Read-only `package.json` fails planned mutation gracefully in apply mode.
- `test_t2_f08_05_unknown_test_framework`: Unrecognized test runner falls back to package manager defaults safely.

### Feature 9 Boundaries: Multi-Language DRA Idempotency
- `test_t2_f09_01_whitespace_insensitivity`: Insignificant whitespace changes in manifests do not trigger false mutations.
- `test_t2_f09_02_reordered_scripts_object`: Scripts in different JSON key orders do not trigger mutation.
- `test_t2_f09_03_partial_script_set_present`: Only missing scripts from the 5-script palette are added; existing ones remain untouched.
- `test_t2_f09_04_empty_manifest_re_run`: Pre-harmonized manifest run 10 times consecutively remains bit-identical.
- `test_t2_f09_05_locked_backup_dir`: Re-running when backup dir is read-only succeeds if 0 mutations are needed.

### Feature 10 Boundaries: Dynamic SPA Route Switching
- `test_t2_f10_01_malformed_url_pathname`: Pathname like `/c/` without ID returns null without throwing.
- `test_t2_f10_02_uuid_with_special_characters`: Conversation IDs with dashes, underscores, and alphanumeric chars parse cleanly.
- `test_t2_f10_03_rapid_consecutive_pushstate`: 50 rapid `pushState` calls within 100ms throttle or sequence properly without race conditions.
- `test_t2_f10_04_non_standard_spa_routes`: Routes like `/settings` or `/agent` do not trigger false conversation reloads.
- `test_t2_f10_05_hash_based_routing`: Hash routing (`/#/c/<id>`) falls back safely without unhandled exceptions.

### Feature 11 Boundaries: Active Subagent Window Detection
- `test_t2_f11_01_multiple_tab_parameters`: Query string containing duplicate `?tab=...` resolves first or active subagent tab.
- `test_t2_f11_02_malformed_subagent_prefix`: Query param `?tab=subagent_convo__` (empty UUID) falls back to route cascade ID.
- `test_t2_f11_03_nested_subagent_uuids`: Subagents spawned by subagents maintain parent hierarchy linkage.
- `test_t2_f11_04_non_subagent_tab`: `?tab=terminal` or `?tab=browser` ignores subagent logic and resolves active conversation ID.
- `test_t2_f11_05_url_encoded_query_params`: `?tab=subagent_convo%5F%5F<uuid>` decodes properly.

### Feature 12 Boundaries: Live ConnectRPC 60 FPS Streaming
- `test_t2_f12_01_oversized_connect_frame`: Stream frame exceeding 64KB reassembles correctly across chunk boundaries.
- `test_t2_f12_02_server_stream_abort`: Premature stream termination or server reset cleans up listener without leaking RAF handle.
- `test_t2_f12_03_empty_stream_deltas`: Heartbeat frames with 0 step deltas do not trigger redundant DOM reflows.
- `test_t2_f12_04_high_frequency_ingress`: 1,000 updates/sec are collapsed into single frame renders at 16.6ms intervals.
- `test_t2_f12_05_missing_csrf_token`: Missing CSRF token falls back to unauthenticated or reports clear diagnostic.

### Feature 13 Boundaries: Live DevTools CDP Controller
- `test_t2_f13_01_port_file_empty`: Empty `DevToolsActivePort` file raises `CDPConnectionError`.
- `test_t2_f13_02_port_file_unreadable`: Unreadable port file raises `CDPConnectionError` with path details.
- `test_t2_f13_03_target_not_found`: Port listening but no matching page target raises `CDPTargetNotFoundError`.
- `test_t2_f13_04_websocket_handshake_timeout`: Unresponsive WebSocket connection aborts cleanly at timeout limit.
- `test_t2_f13_05_evaluate_syntax_error`: JavaScript syntax error in injected snippet returns error object without crashing client.

### Feature 14 Boundaries: E2E Regression & Tier Verification
- `test_t2_f14_01_empty_argv_invokes_help`: Running `agyis` with no arguments prints help and exits with code 0.
- `test_t2_f14_02_unknown_subcommand_exit_code`: Unknown subcommand (e.g. `agyis foobar`) exits with code 2 (argparse error).
- `test_t2_f14_03_unrecognized_arguments_exit_code`: Known subcommand with bad flags exits with code 2.
- `test_t2_f14_04_extreme_environment_variables`: Scrubbed or missing `HOME`/`USER` env vars handled gracefully with safe fallbacks.
- `test_t2_f14_05_signal_interrupt_handling`: Clean exit on SIGINT/KeyboardInterrupt without unhandled stack traces.

---

## 5. Tier 3: Cross-Feature Interactions (14 Pairwise Combinations)

1. `test_t3_c01_harmonize_migration_and_safety_archive`: (F1 x F2) Migrating legacy `.agent/` rules creates `.agents/archive/` backup tarball containing original legacy files.
2. `test_t3_c02_safety_archive_and_tagged_fences`: (F2 x F3) Backup archive created while simultaneously updating `AGENTS.md` tagged fence and sanitizing markdown links.
3. `test_t3_c03_dirty_guard_and_safety_patch`: (F4 x F5) When uncommitted changes exist and `--allow-dirty` is supplied, dirty guard clears and writes `.agents/artifacts/pre_onboard_safety.patch`.
4. `test_t3_c04_safety_patch_and_isolated_branch`: (F5 x F6) Safety patch generated before switching/creating dedicated onboarding branch (`chore/onboard-eval`).
5. `test_t3_c05_monorepo_subproject_and_harmonize`: (F7 x F1) Scoping onboarding to `--subproject packages/react` runs harmonization strictly inside subproject while preserving repo root.
6. `test_t3_c06_monorepo_subproject_and_cache_purge`: (F7 x F6) Subproject onboarding purges `.next/` and `.turbo/` inside subproject directory without affecting unrelated sister packages.
7. `test_t3_c07_dra_harmonize_and_monorepo_subproject`: (F8 x F7) DRA test harmonization detects subproject test framework (`packages/react/package.json`) and writes scoped `.agyis/test_manifest.json`.
8. `test_t3_c08_dra_harmonize_and_idempotency_cycle`: (F8 x F9) Generating test scripts and backup patch on round 1, then running round 2 yields exactly 0 mutations and unchanged patch.
9. `test_t3_c09_spa_route_switch_and_subagent_detection`: (F10 x F11) Navigating from `/c/parent-1` to `/c/parent-2?tab=subagent_convo__sub-1` triggers `agyis:routechange` and prioritizes subagent UUID `sub-1`.
10. `test_t3_c10_subagent_detection_and_connectrpc_stream`: (F11 x F12) Active subagent context extraction feeds directly into `InSituConnectClient.streamConversation(subagentId)`.
11. `test_t3_c11_devtools_cdp_and_spa_route_switch`: (F13 x F10) Injected CDP script evaluates `window.location.href`, captures route transition, and fires reload without page refresh.
12. `test_t3_c12_onboard_dirty_guard_and_harmonize_backup`: (F4 x F2) Onboarding dirty tree with `--allow-dirty` successfully generates both pre-onboard safety patch and legacy harmonization archive.
13. `test_t3_c13_dra_test_harmonize_and_onboard_branch`: (F8 x F6) Dedicated onboarding branch checks out, purges caches, and executes test harmonization with manifest creation.
14. `test_t3_c14_cdp_controller_and_connectrpc_client`: (F13 x F12) CDP script injection passes active `connectRpcPort` into `__PAYLOAD__`, allowing `InSituConnectClient` to connect immediately.

---

## 6. Tier 4: Real-World Scenarios (7 Application Workloads)

1. `test_t4_s01_modmail_bot_python_harmonization`: Real-world Discord bot repository (/home/kuasha/Dev/ModMail-Bot) legacy `.agent/` migration, rules upgrade, and skill frontmatter synthesis.
2. `test_t4_s02_purrfect_download_manager_tauri_harmonization`: Hybrid Rust/Svelte desktop app (/home/kuasha/Dev/purrfect-download-manager) migration with `--apply --backup` archive creation and desktop GUI skill provisioning.
3. `test_t4_s03_dream_emirates_app_dirty_onboarding`: React Native mobile repo (/home/kuasha/Dev/dream-emirates-app) uncommitted working tree onboarding with `--allow-dirty`, safety patch generation, and branch isolation.
4. `test_t4_s04_chakra_ui_monorepo_subproject_onboarding`: Monorepo repository (/home/kuasha/Dev/chakra-ui) subproject targeting with `--subproject packages/react`, scoped cache purging, and localized rule fencing.
5. `test_t4_s05_immortal_rust_cargo_test_harmonization`: Pure Rust workspace (/home/kuasha/Dev/immortal) cargo test audit, diff script injection, and `.agyis/test_manifest.json` generation.
6. `test_t4_s06_jimha_node_vitest_test_harmonization`: Fullstack TypeScript repo (/home/kuasha/Dev/jimha) Vitest runner audit, package manager detection (`pnpm`), and backup patch creation.
7. `test_t4_s07_live_insitu_hud_dogfooding_session`: Real Antigravity webview session simulation with dynamic `/c/:id` route transitions, active subagent tab extraction, and 60 FPS ConnectRPC frame rendering.

---

## 7. Defect Escalation Protocol
When any test discovers a discrepancy between actual code behavior and this specification:
1. Immediately log an on-the-spot defect using the standard `[DEFECT_REPORT]` block format:
   ```json
   [DEFECT_REPORT]
   {
     "quadrant": "Q1: Real Projects" | "Q4: Live HUD",
     "severity": "P0" | "P1" | "P2" | "P3",
     "title": "Short descriptive summary",
     "reproduction_command": "CLI invocation or test method",
     "observed_behavior": "What the code currently does",
     "expected_behavior": "What the specification requires",
     "remediation_plan": "Specific files and lines to modify"
   }
   [/DEFECT_REPORT]
   ```
2. Escalate directly to the dispatching orchestrator and implementing agent without modifying implementation code.
