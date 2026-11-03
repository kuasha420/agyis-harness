# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Unit & Contract Tests for Forensic RE & Dirtyroom Diagnostics (Issue #100, ADR-028).
Validates context-aware workspace detection, profile selection, doctor integration,
and non-destructive auto-healing under sub-second benchmark SLAs.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from harness.runtime.doctor import DEFAULT_MATRIX, print_cli_report, run_doctor
from harness.runtime.healing import heal_environment, heal_forensic_toolchain
from harness.runtime.re_checks import (
    FORENSIC_PACKAGE_MAP,
    audit_forensic_toolchain,
    get_dirtyroom_profile,
    is_re_workspace,
    probe_binary_with_version,
)


class TestReDoctorWorkspaceDetection(unittest.TestCase):
    """Verifies context-aware RE workspace detection."""

    def test_is_re_workspace_clean_directory_is_false(self):
        with tempfile.TemporaryDirectory() as td:
            clean_dir = Path(td)
            self.assertFalse(is_re_workspace(clean_dir))

    def test_is_re_workspace_with_dirtyroom_dir(self):
        with tempfile.TemporaryDirectory() as td:
            dr = Path(td) / ".dirtyroom"
            dr.mkdir()
            self.assertTrue(is_re_workspace(Path(td)))
            # Nested subdirectory also detects parent .dirtyroom
            nested = Path(td) / "src" / "sub"
            nested.mkdir(parents=True)
            self.assertTrue(is_re_workspace(nested))

    def test_is_re_workspace_with_cleanroom_policy_file(self):
        with tempfile.TemporaryDirectory() as td:
            spec_dir = Path(td) / "docs" / "specs"
            spec_dir.mkdir(parents=True)
            (spec_dir / "CLEANROOM_POLICY.md").write_text("# Cleanroom Policy\n", encoding="utf-8")
            self.assertTrue(is_re_workspace(Path(td)))

    def test_is_re_workspace_env_var_override(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {"AGYIS_DIRTYROOM": "1"}):
                self.assertTrue(is_re_workspace(Path(td)))


class TestDirtyroomProfileResolution(unittest.TestCase):
    """Verifies parsing of profile configurations from dirtyroom.env and environment variables."""

    def test_default_profile_is_static_cleanroom(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(get_dirtyroom_profile(Path(td)), "static-cleanroom")

    def test_profile_from_dirtyroom_env_file(self):
        with tempfile.TemporaryDirectory() as td:
            dr = Path(td) / ".dirtyroom"
            dr.mkdir()
            env_file = dr / "dirtyroom.env"
            env_file.write_text("PROFILE=dynamic-game-harness\n", encoding="utf-8")
            self.assertEqual(get_dirtyroom_profile(Path(td)), "dynamic-game-harness")

    def test_profile_env_var_override(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {"AGYIS_RE_PROFILE": "full"}):
                self.assertEqual(get_dirtyroom_profile(Path(td)), "full")


class TestForensicProbe(unittest.TestCase):
    """Verifies binary version probes and timeouts."""

    def test_probe_binary_missing_returns_none(self):
        cand, ver = probe_binary_with_version("non_existent_binary_psl_404_xyz")
        self.assertIsNone(cand)
        self.assertIsNone(ver)

    def test_probe_binary_extracts_semver(self):
        with patch("shutil.which", return_value="/usr/bin/mocktool"):
            mock_proc = MagicMock()
            mock_proc.stdout = "mocktool version 2.47.1 (Linux-gnu)"
            mock_proc.stderr = ""
            with patch("subprocess.run", return_value=mock_proc):
                cand, ver = probe_binary_with_version("mocktool")
                self.assertEqual(cand, "/usr/bin/mocktool")
                self.assertEqual(ver, "2.47.1")


class TestAuditForensicToolchain(unittest.TestCase):
    """Verifies static vs dynamic profile auditing and missing package reporting."""

    def test_static_profile_marks_missing_dynamic_tools_as_info(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("shutil.which", return_value=None), \
                 patch("harness.runtime.re_checks.find_ghidra_headless", return_value=None), \
                 patch("harness.runtime.re_checks.find_jdk21_path", return_value=None), \
                 patch("harness.runtime.re_checks.check_patch", return_value={"status": "not_installed"}):
                res = audit_forensic_toolchain(workspace_dir=Path(td), profile="static-cleanroom")
                self.assertEqual(res["profile"], "static-cleanroom")
                tool_dict = {t["name"]: t for t in res["tools"]}
                # Dynamic tools should be INFO, not WARN
                self.assertEqual(tool_dict["tshark"]["status"], "INFO")
                self.assertEqual(tool_dict["ydotoold"]["status"], "INFO")
                self.assertEqual(tool_dict["xdotool"]["status"], "INFO")
                self.assertEqual(tool_dict["gpu-screen-recorder"]["status"], "INFO")

    def test_dynamic_profile_marks_missing_dynamic_tools_as_warn(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("shutil.which", return_value=None), \
                 patch("harness.runtime.re_checks.find_ghidra_headless", return_value=None), \
                 patch("harness.runtime.re_checks.find_jdk21_path", return_value=None), \
                 patch("harness.runtime.re_checks.check_patch", return_value={"status": "not_installed"}):
                res = audit_forensic_toolchain(workspace_dir=Path(td), profile="dynamic-game-harness")
                self.assertEqual(res["profile"], "dynamic-game-harness")
                tool_dict = {t["name"]: t for t in res["tools"]}
                self.assertEqual(tool_dict["tshark"]["status"], "WARN")
                self.assertEqual(tool_dict["ydotoold"]["status"], "WARN")
                self.assertEqual(tool_dict["xdotool"]["status"], "WARN")
                self.assertEqual(tool_dict["gpu-screen-recorder"]["status"], "WARN")
                self.assertIn("tshark", res["missing_packages"])
                self.assertIn("ydotoold", res["missing_packages"])


class TestDoctorForensicIntegration(unittest.TestCase):
    """Verifies integration into run_doctor and cli rendering."""

    def test_run_doctor_omits_forensic_toolchain_in_regular_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            audit = run_doctor(DEFAULT_MATRIX, workspace_root=Path(td), re_toolchain=False)
            self.assertFalse(audit["re_toolchain"])
            self.assertIsNone(audit["forensic_toolchain"])

    def test_run_doctor_includes_forensic_toolchain_when_flag_passed(self):
        with tempfile.TemporaryDirectory() as td:
            audit = run_doctor(DEFAULT_MATRIX, workspace_root=Path(td), re_toolchain=True)
            self.assertTrue(audit["re_toolchain"])
            self.assertIsNotNone(audit["forensic_toolchain"])
            self.assertIn("tools", audit["forensic_toolchain"])

    def test_run_doctor_auto_activates_in_re_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            dr = Path(td) / ".dirtyroom"
            dr.mkdir()
            audit = run_doctor(DEFAULT_MATRIX, workspace_root=Path(td), re_toolchain=False)
            self.assertTrue(audit["re_toolchain"])
            self.assertIsNotNone(audit["forensic_toolchain"])

    def test_print_cli_report_renders_forensic_section(self):
        mock_audit = {
            "os_family": "arch",
            "hermetic_python_available": None,
            "cli_binary": {"status": "OK", "details": "ok"},
            "tiers": {},
            "summary": {"ok": 5, "warning": 0, "outdated": 0, "missing": 0, "optional_missing": 0},
            "forensic_toolchain": {
                "profile": "dynamic-game-harness",
                "tools": [
                    {
                        "name": "ghidra",
                        "category": "core",
                        "status": "PASS",
                        "path": "/opt/ghidra/support/analyzeHeadless",
                        "version": "headless-ready",
                    },
                    {
                        "name": "tshark",
                        "category": "dynamic",
                        "status": "WARN",
                        "path": None,
                        "version": None,
                    },
                ],
                "remediation": ["Install wireshark-cli"],
            },
        }
        with patch("sys.stdout") as mock_stdout:
            print_cli_report(mock_audit)


class TestForensicAutoHealing(unittest.TestCase):
    """Verifies non-destructive user-space auto-healing for RE and dirtyroom."""

    def test_heal_forensic_toolchain_applies_patch(self):
        mock_audit = {
            "os_family": "arch",
            "forensic_toolchain": {
                "tools": [{"name": "rea_patch", "status": "WARN"}],
                "missing_packages": [],
            },
        }
        with patch("harness.re.patcher.check_patch", return_value={"status": "unapplied"}), \
             patch("harness.re.patcher.apply_patch", return_value={"success": True, "applied_files": ["f1", "f2"]}):
            actions = heal_forensic_toolchain(mock_audit)
            self.assertTrue(any("Auto-applied REA Ghidra acceleration patch" in a for a in actions))

    def test_heal_forensic_toolchain_inits_missing_db(self):
        with tempfile.TemporaryDirectory() as td:
            dr = Path(td) / ".dirtyroom"
            dr.mkdir()
            (dr / "symbols").mkdir()
            mock_audit = {
                "os_family": "debian",
                "forensic_toolchain": {
                    "tools": [{"name": "dirtyroom_db", "version": "missing_db"}],
                    "missing_packages": [],
                },
            }
            actions = heal_forensic_toolchain(mock_audit, workspace_dir=Path(td))
            self.assertTrue(any("Auto-initialized dirty-room SQLite" in a for a in actions))
            self.assertTrue((dr / "symbols" / "dirtyroom.db").is_file())

    def test_heal_forensic_toolchain_distro_packages_arch(self):
        mock_audit = {
            "os_family": "arch",
            "forensic_toolchain": {
                "tools": [],
                "missing_packages": ["tshark", "ydotoold"],
            },
        }
        actions = heal_forensic_toolchain(mock_audit)
        expected_cmd = "sudo pacman -S wireshark-cli ydotool"
        self.assertTrue(any(expected_cmd in a for a in actions))

    def test_heal_forensic_toolchain_distro_packages_debian(self):
        mock_audit = {
            "os_family": "debian",
            "forensic_toolchain": {
                "tools": [],
                "missing_packages": ["tshark", "ydotoold"],
            },
        }
        actions = heal_forensic_toolchain(mock_audit)
        expected_cmd = "sudo apt update && sudo apt install -y tshark ydotool"
        self.assertTrue(any(expected_cmd in a for a in actions))


class TestDoctorLatencyInvariant(unittest.TestCase):
    """Asserts sub-second SLA for forensic doctor inspection (ADR-015)."""

    def test_audit_forensic_toolchain_sub_second_latency(self):
        t0 = time.perf_counter()
        audit_forensic_toolchain()
        dur = time.perf_counter() - t0
        self.assertLess(dur, 0.75, f"Audit took {dur:.4f}s which violates sub-second benchmark SLA")


if __name__ == "__main__":
    unittest.main()
