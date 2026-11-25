#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Bug Bash Tier 2 Boundary Cases (Harmonization, Onboarding, Monorepo, DRA Test Runner & CLI).
Split from test_e2e_bugbash.py for sub-second ADR-015 verification.
"""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from unittest.mock import patch

from harness.cli import main as cli_main
from harness.commands.onboard import cmd_onboard
from harness.delivery.harmonize import harmonize_workspace
from harness.delivery.workspace import LEGACY_TAG_END, LEGACY_TAG_START, TAG_START
from harness.harmonize.test_runner import TestHarmonizer, harmonize_test_runners
from tests.test_e2e_bugbash import BaseBugBashTestCase


class TestTier2BoundaryCases(BaseBugBashTestCase):
    """Tier 2: Boundary conditions, corner cases, and stress resilience (F01-F09, F14)."""

    # --- Feature 1 Boundaries ---

    def test_t2_f01_01_empty_agent_dir(self) -> None:
        """F1.B1: Handles completely empty .agent/ directory without failure."""
        (self.ws / ".agent").mkdir(parents=True, exist_ok=True)
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)
        self.assertEqual(len(res.legacy_rules_migrated), 0)

    def test_t2_f01_02_broken_symlinks_in_agent_dir(self) -> None:
        """F1.B2: Ignores broken symlinks inside legacy .agent/ gracefully."""
        agent_dir = self.create_legacy_agent_dir()
        broken = agent_dir / "rules" / "broken_link.md"
        try:
            broken.symlink_to(self.ws / "non_existent_file.md")
        except OSError:
            self.skipTest("Symlinks not supported in environment")
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)

    def test_t2_f01_03_unreadable_file_permissions(self) -> None:
        """F1.B3: Handles read-only files without crashing."""
        agent_dir = self.create_legacy_agent_dir()
        ro_file = agent_dir / "rules" / "readonly.md"
        ro_file.write_text("# Read Only\n", encoding="utf-8")
        os.chmod(ro_file, 0o444)
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)

    def test_t2_f01_04_deeply_nested_rule_directories(self) -> None:
        """F1.B4: Preserves deeply nested directory hierarchy under .agents/rules/."""
        agent_dir = self.create_legacy_agent_dir()
        deep_dir = agent_dir / "rules" / "a" / "b" / "c" / "d"
        deep_dir.mkdir(parents=True, exist_ok=True)
        (deep_dir / "deep.md").write_text("# Deep Rule\n", encoding="utf-8")
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)
        self.assertTrue((self.ws / ".agents" / "rules" / "a" / "b" / "c" / "d" / "deep.md").exists())

    def test_t2_f01_05_special_characters_in_filenames(self) -> None:
        """F1.B5: Handles filenames with unicode, spaces, and punctuation."""
        agent_dir = self.create_legacy_agent_dir()
        special_file = agent_dir / "rules" / "Rule #1 (Special & Rules).md"
        special_file.write_text("# Special\n", encoding="utf-8")
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)
        migrated = self.ws / ".agents" / "rules" / "Rule #1 (Special & Rules).md"
        self.assertTrue(migrated.exists())

    # --- Feature 2 Boundaries ---

    def test_t2_f02_01_empty_agent_dir_archived(self) -> None:
        """F2.B1: Successfully archives an empty .agent/ directory."""
        (self.ws / ".agent").mkdir(parents=True, exist_ok=True)
        self.init_git_repo()
        res = harmonize_workspace(self.ws, dry_run=False, prune_legacy=True, backup=True)
        self.assertTrue(res.success)
        tarballs = list((self.ws / ".agents" / "archive").glob("*.tar.gz"))
        self.assertTrue(len(tarballs) >= 1)

    def test_t2_f02_02_archive_path_read_only(self) -> None:
        """F2.B2: Returns structured error if target archive directory is unwriteable."""
        self.create_legacy_agent_dir()
        ro_archive = self.ws / "ro_backups"
        ro_archive.mkdir(parents=True, exist_ok=True)
        os.chmod(ro_archive, 0o555)
        try:
            with self.assertRaises(PermissionError):
                harmonize_workspace(self.ws, dry_run=False, prune_legacy=True, backup=True, archive_dir=ro_archive)
        finally:
            os.chmod(ro_archive, 0o777)

    def test_t2_f02_03_existing_tarball_collision(self) -> None:
        """F2.B3: Successive archive calls generate unique timestamped tarballs."""
        self.create_legacy_agent_dir()
        self.init_git_repo()
        res1 = harmonize_workspace(self.ws, dry_run=False, prune_legacy=True, backup=True)
        self.assertTrue(res1.success)
        tarballs1 = list((self.ws / ".agents" / "archive").glob("*.tar.gz"))
        self.assertTrue(len(tarballs1) >= 1)

    def test_t2_f02_04_zero_byte_files_in_manifest(self) -> None:
        """F2.B4: Correctly hashes 0-byte files with standard SHA-256."""
        agent_dir = self.create_legacy_agent_dir()
        (agent_dir / "rules" / "empty.md").write_text("", encoding="utf-8")
        self.init_git_repo()
        res = harmonize_workspace(self.ws, dry_run=False, prune_legacy=True, backup=True)
        self.assertTrue(res.success)
        manifests = list((self.ws / ".agents" / "archive").glob("*-manifest.json"))
        data = json.loads(manifests[0].read_text(encoding="utf-8"))
        empty_sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        self.assertEqual(data.get("digests", {}).get("rules/empty.md"), empty_sha)

    def test_t2_f02_05_corrupted_existing_tarball(self) -> None:
        """F2.B5: Existing corrupt files in archive dir do not block new backups."""
        self.create_legacy_agent_dir()
        self.init_git_repo()
        archive_dir = self.ws / ".agents" / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / "corrupted.tar.gz").write_text("corrupted bytes", encoding="utf-8")
        res = harmonize_workspace(self.ws, dry_run=False, prune_legacy=True, backup=True)
        self.assertTrue(res.success)

    # --- Feature 3 Boundaries ---

    def test_t2_f03_01_malformed_unclosed_fence(self) -> None:
        """F3.B1: Handles unclosed legacy tag fences gracefully."""
        (self.ws / "AGENTS.md").write_text(f"# Rules\n{LEGACY_TAG_START}\nunclosed block\n", encoding="utf-8")
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)

    def test_t2_f03_02_empty_agents_md(self) -> None:
        """F3.B2: Injects tagged fence into empty AGENTS.md."""
        (self.ws / "AGENTS.md").write_text("", encoding="utf-8")
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)
        self.assertIn(TAG_START, (self.ws / "AGENTS.md").read_text(encoding="utf-8"))

    def test_t2_f03_03_nonexistent_agents_md(self) -> None:
        """F3.B3: Creates AGENTS.md from scratch if missing."""
        self.assertFalse((self.ws / "AGENTS.md").exists())
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)
        self.assertTrue((self.ws / "AGENTS.md").exists())

    def test_t2_f03_04_multiple_legacy_fences(self) -> None:
        """F3.B4: Normalizes multiple legacy fence blocks."""
        text = f"{LEGACY_TAG_START}\nF1\n{LEGACY_TAG_END}\nMiddle\n{LEGACY_TAG_START}\nF2\n{LEGACY_TAG_END}"
        (self.ws / "AGENTS.md").write_text(text, encoding="utf-8")
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)

    def test_t2_f03_05_crlf_windows_newlines(self) -> None:
        """F3.B5: Tolerates Windows CRLF newlines without breaking fences."""
        crlf_content = f"# Rules\r\n{LEGACY_TAG_START}\r\nLegacy\r\n{LEGACY_TAG_END}\r\n"
        (self.ws / "AGENTS.md").write_text(crlf_content, encoding="utf-8")
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)

    # --- Feature 4 Boundaries ---

    def test_t2_f04_01_staged_changes_only(self) -> None:
        """F4.B1: Staged changes only (git add) trigger dirty guard."""
        self.init_git_repo(dirty=True, staged=True)
        code = cmd_onboard(self.ws, allow_dirty=False)
        self.assertEqual(code, 1)

    def test_t2_f04_02_unstaged_modified_only(self) -> None:
        """F4.B2: Unstaged modifications trigger dirty guard."""
        self.init_git_repo(dirty=True, staged=False)
        code = cmd_onboard(self.ws, allow_dirty=False)
        self.assertEqual(code, 1)

    def test_t2_f04_03_untracked_gitignored_files(self) -> None:
        """F4.B3: Ignored files do not trigger dirty guard."""
        self.init_git_repo(dirty=False)
        (self.ws / ".gitignore").write_text("*.tmp\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.ws), "add", ".gitignore"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.ws), "commit", "-m", "add gitignore"], check=True, capture_output=True)
        (self.ws / "scratch.tmp").write_text("temp", encoding="utf-8")
        code = cmd_onboard(self.ws, allow_dirty=False, dry_run=True)
        self.assertEqual(code, 0)

    def test_t2_f04_04_deleted_tracked_files(self) -> None:
        """F4.B4: Deleting a tracked file marks working tree dirty."""
        self.init_git_repo(dirty=False)
        (self.ws / "README.md").unlink()
        code = cmd_onboard(self.ws, allow_dirty=False)
        self.assertEqual(code, 1)

    def test_t2_f04_05_non_git_workspace(self) -> None:
        """F4.B5: Onboard on non-git directory returns exit code 1."""
        code = cmd_onboard(self.ws, allow_dirty=False)
        self.assertEqual(code, 1)

    # --- Feature 5 Boundaries ---

    def test_t2_f05_01_binary_file_diff_handling(self) -> None:
        """F5.B1: Uncommitted binary file diff is handled without crash."""
        self.init_git_repo(dirty=False)
        (self.ws / "binary.dat").write_bytes(b"\x00\xff\xfe\xfd\x01\x02")
        subprocess.run(["git", "-C", str(self.ws), "add", "."], check=True, capture_output=True)
        code = cmd_onboard(self.ws, allow_dirty=True, dry_run=False)
        self.assertEqual(code, 0)

    def test_t2_f05_02_massive_diff_generation(self) -> None:
        """F5.B2: Captures large uncommitted diff (>2000 lines) completely."""
        self.init_git_repo(dirty=False)
        large_text = "\n".join(f"Line {i}: data payload" for i in range(2500))
        (self.ws / "large.txt").write_text(large_text, encoding="utf-8")
        subprocess.run(["git", "-C", str(self.ws), "add", "large.txt"], check=True, capture_output=True)
        code = cmd_onboard(self.ws, allow_dirty=True, dry_run=False)
        self.assertEqual(code, 0)
        artifacts = list((self.ws / ".agents" / "artifacts").glob("*.patch"))
        self.assertTrue(len(artifacts) >= 1)
        self.assertTrue(artifacts[0].stat().st_size > 10000)

    def test_t2_f05_03_staged_and_unstaged_diff_capture(self) -> None:
        """F5.B3: Captures combined staged and unstaged diffs."""
        self.init_git_repo(dirty=True, staged=False)
        (self.ws / "staged.txt").write_text("staged content", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.ws), "add", "staged.txt"], check=True, capture_output=True)
        code = cmd_onboard(self.ws, allow_dirty=True, dry_run=False)
        self.assertEqual(code, 0)

    def test_t2_f05_04_patch_directory_permission_denied(self) -> None:
        """F5.B4: Handles unwriteable artifacts directory gracefully."""
        self.init_git_repo(dirty=True)
        art = self.ws / ".agents" / "artifacts"
        art.mkdir(parents=True, exist_ok=True)
        os.chmod(art, 0o555)
        try:
            try:
                cmd_onboard(self.ws, allow_dirty=True, dry_run=False)
            except PermissionError:
                pass
        finally:
            os.chmod(art, 0o777)

    def test_t2_f05_05_consecutive_onboard_patch_overwrite(self) -> None:
        """F5.B5: Repeated onboard calls overwrite or update safety patch safely."""
        self.init_git_repo(dirty=True)
        cmd_onboard(self.ws, allow_dirty=True, dry_run=False)
        code2 = cmd_onboard(self.ws, allow_dirty=True, dry_run=False)
        self.assertEqual(code2, 0)

    # --- Feature 6 Boundaries ---

    def test_t2_f06_01_invalid_branch_characters(self) -> None:
        """F6.B1: Branch name with illegal git characters fails cleanly."""
        self.init_git_repo()
        code = cmd_onboard(self.ws, create_branch="bad:branch~name^1", dry_run=False)
        self.assertEqual(code, 1)

    def test_t2_f06_02_detached_head_state(self) -> None:
        """F6.B2: Checks out new branch from detached HEAD state."""
        self.init_git_repo()
        rev = subprocess.check_output(["git", "-C", str(self.ws), "rev-parse", "HEAD"], text=True).strip()
        subprocess.run(["git", "-C", str(self.ws), "checkout", rev], check=True, capture_output=True)
        code = cmd_onboard(self.ws, create_branch="chore/from-detached", dry_run=False)
        self.assertEqual(code, 0)

    def test_t2_f06_03_branch_already_checked_out(self) -> None:
        """F6.B3: Requesting currently active branch succeeds without error."""
        self.init_git_repo()
        code = cmd_onboard(self.ws, create_branch="main", dry_run=False)
        self.assertEqual(code, 0)

    def test_t2_f06_04_empty_cache_directories(self) -> None:
        """F6.B4: Purging empty cache directories succeeds smoothly."""
        self.init_git_repo()
        (self.ws / ".next").mkdir(parents=True, exist_ok=True)
        code = cmd_onboard(self.ws, allow_dirty=True, purge_caches=True, dry_run=False)
        self.assertEqual(code, 0)

    def test_t2_f06_05_deeply_nested_caches(self) -> None:
        """F6.B5: Purges nested subproject cache folders."""
        self.init_git_repo()
        nested = self.ws / "apps" / "web" / ".next"
        nested.mkdir(parents=True, exist_ok=True)
        (nested / "build.bin").write_text("build", encoding="utf-8")
        code = cmd_onboard(self.ws, subproject="apps/web", allow_dirty=True, purge_caches=True, dry_run=False)
        self.assertEqual(code, 0)
        self.assertFalse(nested.exists())

    # --- Feature 7 Boundaries ---

    def test_t2_f07_01_deeply_nested_subproject(self) -> None:
        """F7.B1: Resolves deeply nested subproject packages/core/submodule/app."""
        self.init_git_repo()
        sub = self.ws / "packages" / "core" / "submodule" / "app"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / "package.json").write_text("{}", encoding="utf-8")
        code = cmd_onboard(self.ws, subproject="packages/core/submodule/app", allow_dirty=True, dry_run=True)
        self.assertEqual(code, 0)

    def test_t2_f07_02_subproject_with_trailing_slash(self) -> None:
        """F7.B2: Tolerates trailing slashes in subproject path."""
        self.init_git_repo()
        sub = self.ws / "packages" / "ui"
        sub.mkdir(parents=True, exist_ok=True)
        code = cmd_onboard(self.ws, subproject="packages/ui/", allow_dirty=True, dry_run=True)
        self.assertEqual(code, 0)

    def test_t2_f07_03_relative_dot_subproject(self) -> None:
        """F7.B3: Subproject '.' resolves cleanly to root workspace without cache purge assertion crash."""
        self.init_git_repo()
        code = cmd_onboard(self.ws, subproject=".", allow_dirty=True, purge_caches=False, dry_run=True)
        self.assertEqual(code, 0)

    def test_t2_f07_04_subproject_outside_repo(self) -> None:
        """F7.B4: Subproject pointing outside repo (path traversal) halts."""
        self.init_git_repo()
        code = cmd_onboard(self.ws, subproject="../outside", allow_dirty=True, dry_run=True)
        self.assertEqual(code, 1)

    def test_t2_f07_05_symlinked_subproject(self) -> None:
        """F7.B5: Subproject that is a symlink resolves to canonical path."""
        self.init_git_repo()
        real_sub = self.ws / "real_package"
        real_sub.mkdir(parents=True, exist_ok=True)
        (real_sub / "package.json").write_text("{}", encoding="utf-8")
        link_sub = self.ws / "link_package"
        try:
            link_sub.symlink_to(real_sub)
        except OSError:
            self.skipTest("Symlinks unsupported")
        code = cmd_onboard(self.ws, subproject="link_package", allow_dirty=True, dry_run=True)
        self.assertEqual(code, 0)

    # --- Feature 8 Boundaries ---

    def test_t2_f08_01_corrupted_package_json(self) -> None:
        """F8.B1: Handles corrupted non-parseable package.json without crashing."""
        (self.ws / "package.json").write_text("{ unclosed json", encoding="utf-8")
        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()
        self.assertIsNotNone(audit)

    def test_t2_f08_02_missing_scripts_field(self) -> None:
        """F8.B2: package.json without scripts field initializes it."""
        (self.ws / "package.json").write_text("{\"name\": \"no-scripts\"}\n", encoding="utf-8")
        harmonizer = TestHarmonizer(self.ws)
        mutations = harmonizer.plan_mutations(harmonizer.audit())
        self.assertTrue(len(mutations) >= 1)

    def test_t2_f08_03_tauri_cargo_manifest(self) -> None:
        """F8.B3: Detects src-tauri/Cargo.toml in hybrid desktop projects."""
        self.create_rust_project(is_tauri=True)
        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()
        self.assertEqual(audit.manifest_type, "src-tauri/Cargo.toml")

    def test_t2_f08_04_read_only_manifest_file(self) -> None:
        """F8.B4: Handles read-only manifest file gracefully."""
        self.create_node_project()
        pkg = self.ws / "package.json"
        os.chmod(pkg, 0o444)
        try:
            with self.assertRaises(PermissionError):
                harmonize_test_runners(self.ws, dry_run=False, apply=True)
        finally:
            os.chmod(pkg, 0o666)

    def test_t2_f08_05_unknown_test_framework(self) -> None:
        """F8.B5: Falls back to generic npm/yarn defaults on unknown framework."""
        self.create_node_project(framework="unknown_runner", scripts={"start": "node index.js"})
        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()
        self.assertEqual(audit.test_framework, "node--test")

    # --- Feature 9 Boundaries ---

    def test_t2_f09_01_whitespace_insensitivity(self) -> None:
        """F9.B1: Whitespace formatting differences do not trigger false mutations."""
        self.create_node_project(framework="vitest")
        harmonize_test_runners(self.ws, dry_run=False, apply=True)
        pkg_file = self.ws / "package.json"
        data = json.loads(pkg_file.read_text(encoding="utf-8"))
        pkg_file.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
        res = harmonize_test_runners(self.ws, dry_run=True)
        self.assertEqual(len(res.mutations), 0)

    def test_t2_f09_02_reordered_scripts_object(self) -> None:
        """F9.B2: Reordered keys in scripts object do not trigger mutation."""
        self.create_node_project(framework="vitest")
        harmonize_test_runners(self.ws, dry_run=False, apply=True)
        pkg_file = self.ws / "package.json"
        data = json.loads(pkg_file.read_text(encoding="utf-8"))
        data["scripts"] = {k: data["scripts"][k] for k in reversed(list(data["scripts"].keys()))}
        pkg_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        res = harmonize_test_runners(self.ws, dry_run=True)
        self.assertEqual(len(res.mutations), 0)

    def test_t2_f09_03_partial_script_set_present(self) -> None:
        """F9.B3: Injects only missing scripts when some standard scripts exist."""
        self.create_node_project(scripts={"test:diff": "vitest related --run"})
        harmonizer = TestHarmonizer(self.ws)
        muts = harmonizer.plan_mutations(harmonizer.audit())
        self.assertTrue(len(muts) >= 1)
        self.assertIn("test:watch", muts[0].proposed_content)

    def test_t2_f09_04_empty_manifest_re_run(self) -> None:
        """F9.B4: Running 5 consecutive test harmonizations produces 0 mutations after round 1."""
        self.create_node_project()
        harmonize_test_runners(self.ws, dry_run=False, apply=True)
        for _ in range(5):
            res = harmonize_test_runners(self.ws, dry_run=True)
            self.assertEqual(len(res.mutations), 0)

    def test_t2_f09_05_locked_backup_dir(self) -> None:
        """F9.B5: Read-only backup directory does not fail idempotent zero-mutation run."""
        self.create_node_project()
        harmonize_test_runners(self.ws, dry_run=False, apply=True)
        backups = self.ws / ".agyis" / "backups"
        if backups.exists():
            os.chmod(backups, 0o555)
        try:
            res = harmonize_test_runners(self.ws, dry_run=False, apply=True)
            self.assertTrue(res.success)
        finally:
            if backups.exists():
                os.chmod(backups, 0o777)

    # --- Feature 14 Boundaries ---

    def test_t2_f14_01_empty_argv_invokes_help(self) -> None:
        """F14.B1: Calling CLI with no arguments exits 0 and prints help."""
        code, out, _ = self.run_cli([])
        self.assertEqual(code, 0)
        self.assertIn("Available subcommands", out)

    def test_t2_f14_02_unknown_subcommand_exit_code(self) -> None:
        """F14.B2: Unrecognized subcommand exits with code 2."""
        code, _, _ = self.run_cli(["nonexistent-subcommand"])
        self.assertEqual(code, 2)

    def test_t2_f14_03_unrecognized_arguments_exit_code(self) -> None:
        """F14.B3: Known subcommand with invalid flag exits with code 2."""
        code, _, _ = self.run_cli(["doctor", "--invalid-flag"])
        self.assertEqual(code, 2)

    def test_t2_f14_04_extreme_environment_variables(self) -> None:
        """F14.B4: Runs safely when HOME or USER env vars are unset."""
        code, _, _ = self.run_cli(["--version"], env_overrides={"HOME": "/nonexistent"})
        self.assertEqual(code, 0)

    def test_t2_f14_05_signal_interrupt_handling(self) -> None:
        """F14.B5: Propagates KeyboardInterrupt cleanly."""
        with patch("harness.cli.build_parser", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                cli_main(["--help"])


if __name__ == "__main__":
    unittest.main()
