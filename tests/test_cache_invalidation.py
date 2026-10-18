# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic unit tests for standalone build cache invalidation module (Issue #63).
"""

from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
import unittest

from harness.delivery import (
    DEFAULT_CACHE_TARGETS,
    purge_build_caches,
    purge_workspace_build_caches,
)
from harness.delivery.cache import _assert_contained
from harness.delivery.workspace import purge_build_caches as workspace_purge_build_caches


class TestCacheInvalidation(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self._temp_dir.name).resolve()

    def tearDown(self):
        self._temp_dir.cleanup()

    def test_default_cache_targets_constant(self):
        """Verifies DEFAULT_CACHE_TARGETS contains expected targets."""
        self.assertEqual(DEFAULT_CACHE_TARGETS, (".next", ".turbo", "node_modules/.cache"))

    def test_purge_root_caches(self):
        """Verifies .next, .turbo, and node_modules/.cache at workspace root are purged."""
        (self.ws / ".next").mkdir()
        (self.ws / ".next" / "trace").write_text("trace data\n", encoding="utf-8")
        (self.ws / ".turbo").mkdir()
        (self.ws / ".turbo" / "cache.json").write_text("{}\n", encoding="utf-8")
        (self.ws / "node_modules" / ".cache").mkdir(parents=True)
        (self.ws / "node_modules" / ".cache" / "build.bin").write_bytes(b"\x00\x01")

        purged = purge_workspace_build_caches(self.ws)
        self.assertEqual(len(purged), 3)
        self.assertIn(str(self.ws / ".next"), purged)
        self.assertIn(str(self.ws / ".turbo"), purged)
        self.assertIn(str(self.ws / "node_modules" / ".cache"), purged)

        self.assertFalse((self.ws / ".next").exists())
        self.assertFalse((self.ws / ".turbo").exists())
        self.assertFalse((self.ws / "node_modules" / ".cache").exists())
        self.assertTrue((self.ws / "node_modules").exists(), "node_modules parent directory must be preserved")

    def test_purge_monorepo_subprojects(self):
        """Verifies standard monorepo subproject caches are purged."""
        (self.ws / "apps" / "web" / ".next").mkdir(parents=True)
        (self.ws / "packages" / "ui" / ".turbo").mkdir(parents=True)
        (self.ws / "modules" / "core" / "node_modules" / ".cache").mkdir(parents=True)

        # Non-cache files in node_modules must remain untouched
        (self.ws / "node_modules" / "react" / ".next").mkdir(parents=True)

        purged = purge_workspace_build_caches(self.ws)
        self.assertEqual(len(purged), 3)
        self.assertIn(str(self.ws / "apps" / "web" / ".next"), purged)
        self.assertIn(str(self.ws / "packages" / "ui" / ".turbo"), purged)
        self.assertIn(str(self.ws / "modules" / "core" / "node_modules" / ".cache"), purged)

        self.assertFalse((self.ws / "apps" / "web" / ".next").exists())
        self.assertFalse((self.ws / "packages" / "ui" / ".turbo").exists())
        self.assertFalse((self.ws / "modules" / "core" / "node_modules" / ".cache").exists())
        self.assertTrue(
            (self.ws / "node_modules" / "react" / ".next").exists(),
            "node_modules dependencies must never be purged",
        )

    def test_bounded_recursion_depth(self):
        """Verifies traversal stops when rel_depth >= max_depth."""
        # Depth 2: apps/web/.next (rel_depth=2 < 3) -> purged
        (self.ws / "apps" / "web" / ".next").mkdir(parents=True)

        # Depth 4: apps/a/b/c/.next (rel_depth=3 at apps/a/b -> dirs cleared, c not visited)
        deep_cache = self.ws / "apps" / "a" / "b" / "c" / ".next"
        deep_cache.mkdir(parents=True)
        (deep_cache / "data.bin").write_text("data\n", encoding="utf-8")

        purged = purge_workspace_build_caches(self.ws, max_depth=3)
        self.assertIn(str(self.ws / "apps" / "web" / ".next"), purged)
        self.assertNotIn(str(deep_cache), purged)
        self.assertFalse((self.ws / "apps" / "web" / ".next").exists())
        self.assertTrue(deep_cache.exists(), "Deep cache exceeding max_depth must be preserved")

    def test_dry_run_mode(self):
        """Verifies dry-run returns identified cache paths without deleting from disk."""
        (self.ws / ".next").mkdir()
        (self.ws / ".turbo").mkdir()
        (self.ws / "apps" / "docs" / ".next").mkdir(parents=True)

        purged = purge_workspace_build_caches(self.ws, dry_run=True)
        self.assertEqual(len(purged), 3)
        self.assertEqual(
            purged,
            sorted([
                str(self.ws / ".next"),
                str(self.ws / ".turbo"),
                str(self.ws / "apps" / "docs" / ".next"),
            ]),
        )
        self.assertTrue((self.ws / ".next").exists())
        self.assertTrue((self.ws / ".turbo").exists())
        self.assertTrue((self.ws / "apps" / "docs" / ".next").exists())

    def test_safe_symlink_unlinking_external_target(self):
        """Verifies symlinks pointing to external target directories are unlinked without deleting target."""
        with tempfile.TemporaryDirectory() as ext_dir:
            ext_path = Path(ext_dir) / "external_next_cache"
            ext_path.mkdir()
            (ext_path / "sensitive.txt").write_text("precious payload\n", encoding="utf-8")

            link_path = self.ws / ".next"
            link_path.symlink_to(ext_path)
            self.assertTrue(link_path.is_symlink())

            purged = purge_workspace_build_caches(self.ws)
            self.assertIn(str(link_path), purged)
            self.assertFalse(link_path.exists())
            self.assertFalse(link_path.is_symlink())

            # External target and its contents must remain completely intact
            self.assertTrue(ext_path.exists())
            self.assertTrue((ext_path / "sensitive.txt").exists())
            self.assertEqual((ext_path / "sensitive.txt").read_text(encoding="utf-8"), "precious payload\n")

    def test_safe_symlink_dangling(self):
        """Verifies dangling symlinks are unlinked cleanly without errors."""
        broken_link = self.ws / ".turbo"
        broken_link.symlink_to(self.ws / "non_existent_target")
        self.assertTrue(broken_link.is_symlink())
        self.assertFalse(broken_link.exists())

        purged = purge_workspace_build_caches(self.ws)
        self.assertIn(str(broken_link), purged)
        self.assertFalse(broken_link.is_symlink())

    def test_containment_violation_relative_target(self):
        """Verifies path containment assertion fails when relative target escapes workspace."""
        with self.assertRaises(AssertionError) as ctx:
            purge_workspace_build_caches(self.ws, target_dirs=["../../escaped"])
        self.assertIn("Path containment violation", str(ctx.exception))

    def test_containment_violation_absolute_target(self):
        """Verifies path containment assertion fails when absolute target is provided."""
        with self.assertRaises(AssertionError) as ctx:
            purge_workspace_build_caches(self.ws, target_dirs=["/etc/escaped"])
        self.assertIn("Path containment violation", str(ctx.exception))

    def test_containment_violation_symlink_outside_pointing_inside(self):
        """Verifies assertion fails if symlink is located outside workspace pointing inside."""
        with tempfile.TemporaryDirectory() as outside_dir:
            outside_symlink = Path(outside_dir) / "symlink_to_ws"
            outside_symlink.symlink_to(self.ws)
            with self.assertRaises(AssertionError) as ctx:
                _assert_contained(outside_symlink, self.ws)
            self.assertIn("Path containment violation", str(ctx.exception))

    def test_read_only_permissions_chmod_handling(self):
        """Verifies locked files (0o444) and directories (0o555) are removed without PermissionError."""
        ro_dir = self.ws / ".next" / "ro_dir"
        ro_dir.mkdir(parents=True)
        ro_file = ro_dir / "read_only.json"
        ro_file.write_text('{"locked": true}\n', encoding="utf-8")

        os.chmod(ro_file, 0o444)
        os.chmod(ro_dir, 0o555)

        purged = purge_workspace_build_caches(self.ws)
        self.assertIn(str(self.ws / ".next"), purged)
        self.assertFalse((self.ws / ".next").exists())

    def test_file_as_cache_target(self):
        """Verifies a regular file matching cache name is unlinked cleanly."""
        file_target = self.ws / ".next"
        file_target.write_text("single file cache marker\n", encoding="utf-8")
        self.assertTrue(file_target.is_file())

        purged = purge_workspace_build_caches(self.ws)
        self.assertIn(str(file_target), purged)
        self.assertFalse(file_target.exists())

    def test_nonexistent_and_file_workspace(self):
        """Verifies non-existent or non-directory workspace returns [] cleanly."""
        non_existent = self.ws / "does_not_exist"
        self.assertEqual(purge_workspace_build_caches(non_existent), [])

        regular_file = self.ws / "some_file.txt"
        regular_file.write_text("file\n", encoding="utf-8")
        self.assertEqual(purge_workspace_build_caches(regular_file), [])

    def test_empty_workspace(self):
        """Verifies clean workspace with zero matching targets returns [] cleanly."""
        (self.ws / "src").mkdir()
        (self.ws / "src" / "index.ts").write_text("export const x = 1;\n", encoding="utf-8")
        self.assertEqual(purge_workspace_build_caches(self.ws), [])

    def test_subproject_parameter(self):
        """Verifies explicit subproject parameter purges target caches within subproject."""
        sub = self.ws / "apps" / "api"
        (sub / ".next").mkdir(parents=True)

        purged = purge_workspace_build_caches(self.ws, subproject="apps/api")
        self.assertIn(str(sub / ".next"), purged)
        self.assertFalse((sub / ".next").exists())

    def test_alias_and_workspace_delegation(self):
        """Verifies purge_build_caches alias and workspace.py delegation function correctly."""
        (self.ws / ".next").mkdir()
        purged1 = purge_build_caches(self.ws, dry_run=True)
        self.assertIn(str(self.ws / ".next"), purged1)

        purged2 = workspace_purge_build_caches(self.ws, dry_run=True)
        self.assertIn(str(self.ws / ".next"), purged2)
        self.assertEqual(purged1, purged2)

    def test_containment_violation_root_and_empty_targets(self):
        """Verifies root and empty target specifications raise AssertionError and preserve workspace."""
        canary = self.ws / "canary.txt"
        canary.write_text("precious workspace data\n", encoding="utf-8")
        (self.ws / "sub").mkdir(parents=True, exist_ok=True)

        for bad_target in [".", "", "sub/.."]:
            with self.subTest(target=bad_target):
                with self.assertRaises(AssertionError) as ctx:
                    purge_workspace_build_caches(self.ws, target_dirs=[bad_target])
                self.assertIn("Path containment violation", str(ctx.exception))
                self.assertTrue(self.ws.exists(), "Workspace root must not be deleted")
                self.assertTrue(canary.exists(), "Canary file must remain intact")
                self.assertEqual(canary.read_text(encoding="utf-8"), "precious workspace data\n")

    def test_safe_symlink_readonly_parent_external_target_permissions_preserved(self):
        """Verifies symlink in 0o555 parent directory pointing to external file is unlinked without mutating target permissions."""
        with tempfile.TemporaryDirectory() as ext_dir:
            ext_file = Path(ext_dir) / "sensitive_ext.txt"
            ext_file.write_text("protected payload\n", encoding="utf-8")
            os.chmod(ext_file, 0o644)
            orig_mode = stat.S_IMODE(os.stat(ext_file).st_mode)

            parent_dir = self.ws / "apps" / "web"
            parent_dir.mkdir(parents=True)
            link_path = parent_dir / ".next"
            link_path.symlink_to(ext_file)

            os.chmod(parent_dir, 0o555)
            try:
                purged = purge_workspace_build_caches(self.ws)
                self.assertIn(str(link_path), purged)
                self.assertFalse(link_path.exists())
                self.assertFalse(link_path.is_symlink())

                self.assertTrue(ext_file.exists())
                current_mode = stat.S_IMODE(os.stat(ext_file).st_mode)
                self.assertEqual(
                    current_mode,
                    orig_mode,
                    "External file permissions must not be modified by cache purging",
                )
            finally:
                os.chmod(parent_dir, 0o755)

    def test_safe_symlink_readonly_parent_dangling(self):
        """Verifies dangling symlink in 0o555 parent directory is unlinked cleanly."""
        parent_dir = self.ws / "packages" / "ui"
        parent_dir.mkdir(parents=True)
        dangling_link = parent_dir / ".turbo"
        dangling_link.symlink_to(self.ws / "does_not_exist_target")

        os.chmod(parent_dir, 0o555)
        try:
            purged = purge_workspace_build_caches(self.ws)
            self.assertIn(str(dangling_link), purged)
            self.assertFalse(dangling_link.is_symlink())
            self.assertFalse(dangling_link.exists())
        finally:
            os.chmod(parent_dir, 0o755)


if __name__ == "__main__":
    unittest.main()

