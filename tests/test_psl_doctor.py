#!/usr/bin/env python3
"""
Unit tests for pipeline/psl_doctor.py
"""

import json
from pathlib import Path
import tempfile
import unittest

from pipeline.psl_doctor import (
    check_tool,
    detect_os_family,
    find_hermetic_uv_python,
    parse_version,
    run_doctor,
)


class TestPslDoctor(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(parse_version("3.12.8"), (3, 12, 8))
        self.assertEqual(parse_version("10.5"), (10, 5))
        self.assertEqual(parse_version("v20.11.0"), (20, 11, 0))
        self.assertEqual(parse_version("git version 2.55.0"), (2, 55, 0))
        self.assertEqual(parse_version("unknown"), (0,))

    def test_version_comparisons(self):
        self.assertTrue(parse_version("3.12.0") >= parse_version("3.12.0"))
        self.assertTrue(parse_version("3.12.8") > parse_version("3.12.0"))
        self.assertTrue(parse_version("3.10.13") < parse_version("3.12.0"))
        self.assertTrue(parse_version("10.5.0") > parse_version("8.7.0"))

    def test_detect_os_family(self):
        os_fam = detect_os_family()
        self.assertIn(os_fam, ("arch", "debian", "fedora", "darwin", "linux"))

    def test_check_tool_missing(self):
        spec = {
            "binary": "nonexistent_binary_xyz_12345",
            "min_version": "1.0.0",
        }
        res = check_tool("nonexistent", spec)
        self.assertEqual(res["status"], "MISSING")
        self.assertIsNone(res["path"])

    def test_check_tool_optional_missing(self):
        spec = {
            "binary": "nonexistent_binary_xyz_12345",
            "optional": True,
        }
        res = check_tool("optional_nonexistent", spec)
        self.assertEqual(res["status"], "OPTIONAL_MISSING")

    def test_check_tool_existing(self):
        spec = {
            "binary": "git",
            "min_version": "2.0.0",
            "version_command": "git --version",
            "version_regex": r"git version\s+([0-9]+\.[0-9]+\.[0-9]+)",
        }
        res = check_tool("git", spec)
        self.assertEqual(res["status"], "OK")
        self.assertIsNotNone(res["path"])
        self.assertIsNotNone(res["version"])

    def test_find_hermetic_uv_python(self):
        # Verify function executes without crash and returns Path or None
        herm = find_hermetic_uv_python()
        if herm is not None:
            self.assertTrue(herm.exists())
            self.assertTrue(str(herm).endswith("python3"))

    def test_run_doctor_with_canonical_matrix(self):
        matrix_path = Path(__file__).parent.parent / "harness/runtime/matrix.json"
        self.assertTrue(matrix_path.exists())
        audit = run_doctor(matrix_path)

        self.assertIn("os_family", audit)
        self.assertIn("tiers", audit)
        self.assertIn("summary", audit)
        self.assertIn("tier_1_languages", audit["tiers"])
        self.assertIn("tier_2_swe_cli", audit["tiers"])
        self.assertIn("tier_3_mesh_host", audit["tiers"])
        self.assertGreater(audit["summary"]["total_tools"], 5)


if __name__ == "__main__":
    unittest.main()
