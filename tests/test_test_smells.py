# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Comprehensive Hermetic Unit Tests for Static AST Test Smell Linter (Epic #51 Phase 3.1 R1).

Verifies:
- SM001: Zero-State Tautology ($It == 1.0$)
- SM002: Direct React/Vue Component Calls
- SM003: Fake Visual Regression Tests (Fake VRT)
- SM004: Echo Assertions
- SM005: High Mock Density & Boundary Exemptions (socket, subprocess, Docker)
- Escape Pragma (# agyis: no-smell)
- CLI Integration & JSON serialization
- Sub-second performance benchmark (<1.0s)
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from harness.cli import build_parser
from harness.commands.doctor import cmd_doctor
from harness.doctor.test_smells import (
    BoundaryExemptionRecord,
    SmellAuditReport,
    SmellSeverity,
    SmellType,
    TestSmell,
    audit_file_smells,
    audit_workspace_test_smells,
    run_anti_synthetic_doctor,
)


class TestZeroStateTautology(unittest.TestCase):
    """Tests detection of Zero-State Tautologies ($It == 1.0$)."""

    def test_python_pure_mock_assert_called_is_rejected(self):
        code = """
import unittest
from unittest.mock import MagicMock

class TestUserService(unittest.TestCase):
    def test_save_user(self):
        mock_repo = MagicMock()
        mock_repo.save()
        mock_repo.save.assert_called_once()
"""
        smells = audit_file_smells("test_sample.py", content=code)
        self.assertEqual(len(smells), 1)
        self.assertEqual(smells[0].rule_id, SmellType.ZERO_STATE_TAUTOLOGY.value)
        self.assertEqual(smells[0].severity, SmellSeverity.HARD_REJECTION.value)
        self.assertEqual(smells[0].test_name, "test_save_user")
        self.assertIn("It == 1.0", smells[0].message)

    def test_python_assert_call_count_only_is_rejected(self):
        code = """
def test_dispatch_event():
    mock_handler = MagicMock()
    mock_handler()
    assert mock_handler.call_count == 1
"""
        smells = audit_file_smells("test_sample.py", content=code)
        self.assertEqual(len(smells), 1)
        self.assertEqual(smells[0].rule_id, SmellType.ZERO_STATE_TAUTOLOGY.value)
        self.assertEqual(smells[0].severity, SmellSeverity.HARD_REJECTION.value)

    def test_python_mock_and_state_assert_passes(self):
        code = """
import unittest
from unittest.mock import MagicMock

class TestUserService(unittest.TestCase):
    def test_save_user_with_state(self):
        mock_repo = MagicMock()
        mock_repo.save.return_value = True
        result = mock_repo.save()
        mock_repo.save.assert_called_once()
        self.assertTrue(result)
"""
        smells = audit_file_smells("test_sample.py", content=code)
        tautology_smells = [s for s in smells if s.rule_id == SmellType.ZERO_STATE_TAUTOLOGY.value]
        self.assertEqual(len(tautology_smells), 0)

    def test_python_with_raises_counts_as_state_assertion(self):
        code = """
import unittest
from unittest.mock import MagicMock

class TestUserService(unittest.TestCase):
    def test_save_user_fails(self):
        mock_repo = MagicMock()
        with self.assertRaises(ValueError):
            mock_repo.validate()
            raise ValueError("invalid")
        mock_repo.validate.assert_called()
"""
        smells = audit_file_smells("test_sample.py", content=code)
        tautology_smells = [s for s in smells if s.rule_id == SmellType.ZERO_STATE_TAUTOLOGY.value]
        self.assertEqual(len(tautology_smells), 0)

    def test_ts_js_mock_only_is_rejected(self):
        code = """
describe('UserService', () => {
    it('calls save', () => {
        const mockSave = vi.fn();
        mockSave('alice');
        expect(mockSave).toHaveBeenCalledTimes(1);
    });
});
"""
        smells = audit_file_smells("user.test.ts", content=code)
        self.assertEqual(len(smells), 1)
        self.assertEqual(smells[0].rule_id, SmellType.ZERO_STATE_TAUTOLOGY.value)
        self.assertEqual(smells[0].severity, SmellSeverity.HARD_REJECTION.value)

    def test_ts_js_mock_and_state_assertion_passes(self):
        code = """
describe('UserService', () => {
    it('calls save and returns user', () => {
        const mockSave = vi.fn();
        mockSave('alice');
        expect(mockSave).toHaveBeenCalledTimes(1);
        expect(1 + 1).toBe(2);
    });
});
"""
        smells = audit_file_smells("user.test.ts", content=code)
        tautology_smells = [s for s in smells if s.rule_id == SmellType.ZERO_STATE_TAUTOLOGY.value]
        self.assertEqual(len(tautology_smells), 0)


class TestDirectComponentCalls(unittest.TestCase):
    """Tests detection of Direct Component Function Calls vs Mounting (SM002)."""

    def test_tsx_direct_function_call_is_rejected(self):
        code = """
import { Header } from './Header';

describe('HeaderComponent', () => {
    it('renders title directly', () => {
        const vdom = Header({ title: 'Welcome' });
        expect(vdom).toBeDefined();
    });
});
"""
        smells = audit_file_smells("Header.test.tsx", content=code)
        self.assertTrue(any(s.rule_id == SmellType.DIRECT_COMPONENT_CALL.value for s in smells))
        direct_call = [s for s in smells if s.rule_id == SmellType.DIRECT_COMPONENT_CALL.value][0]
        self.assertEqual(direct_call.severity, SmellSeverity.HARD_REJECTION.value)
        self.assertIn("Header", direct_call.message)

    def test_tsx_render_mounting_passes(self):
        code = """
import { render, screen } from '@testing-library/react';
import { Header } from './Header';

describe('HeaderComponent', () => {
    it('mounts header properly', () => {
        render(<Header title="Welcome" />);
        expect(screen.getByText('Welcome')).toBeInTheDocument();
    });
});
"""
        smells = audit_file_smells("Header.test.tsx", content=code)
        direct_call = [s for s in smells if s.rule_id == SmellType.DIRECT_COMPONENT_CALL.value]
        self.assertEqual(len(direct_call), 0)

    def test_standard_js_builtins_not_flagged_as_components(self):
        code = """
describe('Utils', () => {
    it('uses standard builtins', () => {
        const d = new Date();
        const arr = Array(5);
        const p = Promise.resolve(42);
        const str = String(123);
        const num = Number("42");
        expect(arr.length).toBe(5);
    });
});
"""
        smells = audit_file_smells("utils.test.ts", content=code)
        direct_call = [s for s in smells if s.rule_id == SmellType.DIRECT_COMPONENT_CALL.value]
        self.assertEqual(len(direct_call), 0)


class TestFakeVisualRegression(unittest.TestCase):
    """Tests detection of Fake Visual Regression Tests (Fake VRT, SM003)."""

    def test_python_os_path_exists_on_screenshot_is_rejected(self):
        code = """
import os
import unittest

class TestUI(unittest.TestCase):
    def test_home_page_screenshot(self):
        screenshot_file = "artifacts/screenshot_home.png"
        self.assertTrue(os.path.exists(screenshot_file))
"""
        smells = audit_file_smells("test_ui.py", content=code)
        self.assertTrue(any(s.rule_id == SmellType.FAKE_VRT.value for s in smells))
        vrt_smell = [s for s in smells if s.rule_id == SmellType.FAKE_VRT.value][0]
        self.assertEqual(vrt_smell.severity, SmellSeverity.HARD_REJECTION.value)
        self.assertIn("screenshot", vrt_smell.message.lower())

    def test_python_pathlib_exists_on_screenshot_is_rejected(self):
        code = """
from pathlib import Path

def test_vrt_capture():
    img_path = Path("out/screen.jpg")
    assert img_path.exists()
"""
        smells = audit_file_smells("test_vrt.py", content=code)
        self.assertTrue(any(s.rule_id == SmellType.FAKE_VRT.value for s in smells))

    def test_python_vrt_with_real_image_diff_passes(self):
        code = """
import os
import unittest
from PIL import ImageChops

class TestUI(unittest.TestCase):
    def test_home_page_screenshot(self):
        screenshot_file = "screenshot.png"
        self.assertTrue(os.path.exists(screenshot_file))
        diff = ImageChops.difference(img1, img2)
        self.assertFalse(diff.getbbox())
"""
        smells = audit_file_smells("test_ui.py", content=code)
        vrt_smells = [s for s in smells if s.rule_id == SmellType.FAKE_VRT.value]
        self.assertEqual(len(vrt_smells), 0)

    def test_python_os_path_exists_on_non_image_file_passes(self):
        code = """
import os
import unittest

class TestConfig(unittest.TestCase):
    def test_config_generated(self):
        self.assertTrue(os.path.exists("config.json"))
"""
        smells = audit_file_smells("test_config.py", content=code)
        vrt_smells = [s for s in smells if s.rule_id == SmellType.FAKE_VRT.value]
        self.assertEqual(len(vrt_smells), 0)

    def test_ts_js_fake_vrt_is_rejected(self):
        code = """
import fs from 'fs';

describe('VRT', () => {
    it('captures dashboard', async () => {
        expect(fs.existsSync('dashboard.png')).toBe(true);
    });
});
"""
        smells = audit_file_smells("vrt.test.ts", content=code)
        self.assertTrue(any(s.rule_id == SmellType.FAKE_VRT.value for s in smells))

    def test_ts_js_real_vrt_with_toHaveScreenshot_passes(self):
        code = """
describe('VRT', () => {
    it('captures dashboard authentic', async () => {
        await expect(page).toHaveScreenshot('dashboard.png');
    });
});
"""
        smells = audit_file_smells("vrt.test.ts", content=code)
        vrt_smells = [s for s in smells if s.rule_id == SmellType.FAKE_VRT.value]
        self.assertEqual(len(vrt_smells), 0)


class TestEchoAssertions(unittest.TestCase):
    """Tests detection of Echo Assertions (SM004)."""

    def test_python_mock_return_value_dict_mirror_warns(self):
        code = """
import unittest
from unittest.mock import MagicMock

class TestClient(unittest.TestCase):
    def test_get_profile(self):
        mock_api = MagicMock()
        mock_api.get_user.return_value = {"id": "usr_999", "role": "admin"}
        result = mock_api.get_user()
        self.assertEqual(result["id"], "usr_999")
"""
        smells = audit_file_smells("test_client.py", content=code)
        self.assertTrue(any(s.rule_id == SmellType.ECHO_ASSERTION.value for s in smells))
        echo_smell = [s for s in smells if s.rule_id == SmellType.ECHO_ASSERTION.value][0]
        self.assertEqual(echo_smell.severity, SmellSeverity.WARNING.value)
        self.assertIn("Echo Assertion", echo_smell.message)

    def test_python_mock_return_value_literal_assert_warns(self):
        code = """
from unittest.mock import Mock

def test_fetch_status():
    m = Mock(return_value="PENDING")
    res = m()
    assert res == "PENDING"
"""
        smells = audit_file_smells("test_status.py", content=code)
        self.assertTrue(any(s.rule_id == SmellType.ECHO_ASSERTION.value for s in smells))

    def test_python_independent_transformation_passes(self):
        code = """
import unittest
from unittest.mock import MagicMock

class TestCalculator(unittest.TestCase):
    def test_double_val(self):
        mock_source = MagicMock()
        mock_source.get_num.return_value = 10
        raw = mock_source.get_num()
        doubled = raw * 2
        self.assertEqual(doubled, 20)
"""
        smells = audit_file_smells("test_calc.py", content=code)
        echo_smells = [s for s in smells if s.rule_id == SmellType.ECHO_ASSERTION.value]
        self.assertEqual(len(echo_smells), 0)

    def test_ts_js_mock_return_value_echo_warns(self):
        code = """
describe('AuthService', () => {
    it('fetches profile', () => {
        const client = { get: vi.fn().mockReturnValue('tok_123') };
        const res = client.get();
        expect(res).toBe('tok_123');
    });
});
"""
        smells = audit_file_smells("auth.test.ts", content=code)
        self.assertTrue(any(s.rule_id == SmellType.ECHO_ASSERTION.value for s in smells))


class TestMockDensityAndBoundaryExemption(unittest.TestCase):
    """Tests Mock Density warning (SM005) and automatic Boundary Adapter exemptions."""

    def test_business_logic_excessive_mocks_warns(self):
        code = """
import unittest
from unittest.mock import MagicMock

class TestOrderService(unittest.TestCase):
    def test_process_order(self):
        m1 = MagicMock()
        m2 = MagicMock()
        m3 = MagicMock()
        m1.return_value = 1
        m2.return_value = 2
        m3.return_value = 3
        m1()
        m2()
        m3()
        m1.assert_called()
        self.assertEqual(len([1]), 1)
"""
        smells = audit_file_smells("test_order.py", content=code)
        self.assertTrue(any(s.rule_id == SmellType.MOCK_DENSITY_WARNING.value for s in smells))
        mock_density = [s for s in smells if s.rule_id == SmellType.MOCK_DENSITY_WARNING.value][0]
        self.assertEqual(mock_density.severity, SmellSeverity.WARNING.value)

    def test_subprocess_boundary_adapter_waives_mock_density(self):
        code = """
import subprocess
import unittest
from unittest.mock import MagicMock, patch

class TestShellRunner(unittest.TestCase):
    @patch("subprocess.run")
    def test_execute_shell(self, mock_run):
        m1 = MagicMock()
        m2 = MagicMock()
        mock_run.return_value = MagicMock(returncode=0, stdout=b"ok")
        res = subprocess.run(["ls"])
        mock_run.assert_called_once()
        self.assertEqual(res.returncode, 0)
"""
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "test_shell.py"
            f.write_text(code, encoding="utf-8")
            report = audit_workspace_test_smells(target_path=f)
            self.assertEqual(len(report.hard_rejections), 0)
            mock_density_warnings = [w for w in report.warnings if w.rule_id == SmellType.MOCK_DENSITY_WARNING.value]
            self.assertEqual(len(mock_density_warnings), 0)
            self.assertTrue(len(report.exemptions) >= 1)
            self.assertIn("subprocess", report.exemptions[0].reason)

    def test_socket_boundary_adapter_waives_mock_density(self):
        code = """
import socket
import unittest
from unittest.mock import MagicMock, patch

class TestSocketBridge(unittest.TestCase):
    @patch("socket.socket")
    def test_connect(self, mock_sock):
        m1 = MagicMock()
        m2 = MagicMock()
        mock_sock.return_value = m1
        s = socket.socket()
        s.connect(("localhost", 8080))
        self.assertTrue(mock_sock.called)
        self.assertEqual(s, m1)
"""
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "test_socket.py"
            f.write_text(code, encoding="utf-8")
            report = audit_workspace_test_smells(target_path=f)
            mock_density_warnings = [w for w in report.warnings if w.rule_id == SmellType.MOCK_DENSITY_WARNING.value]
            self.assertEqual(len(mock_density_warnings), 0)
            self.assertTrue(len(report.exemptions) >= 1)

    def test_docker_patch_boundary_adapter_waives_mock_density(self):
        code = """
import unittest
from unittest.mock import MagicMock, patch

class TestContainerManager(unittest.TestCase):
    @patch("docker.from_env")
    def test_list_containers(self, mock_docker):
        m1 = MagicMock()
        m2 = MagicMock()
        m3 = MagicMock()
        mock_docker.return_value = m1
        c = mock_docker()
        self.assertEqual(c, m1)
"""
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "test_docker.py"
            f.write_text(code, encoding="utf-8")
            report = audit_workspace_test_smells(target_path=f)
            mock_density_warnings = [w for w in report.warnings if w.rule_id == SmellType.MOCK_DENSITY_WARNING.value]
            self.assertEqual(len(mock_density_warnings), 0)
            self.assertTrue(len(report.exemptions) >= 1)

    def test_boundary_adapter_still_enforces_hard_rejections(self):
        # A boundary adapter that contains constant tautologies (e.g. assert 1 == 1)
        # must still be rejected. Exemption only waives mock-only interactions and mock density!
        code = """
import subprocess
import unittest
from unittest.mock import MagicMock

class TestSubprocessAdapter(unittest.TestCase):
    def test_run_cmd(self):
        mock_sub = MagicMock()
        mock_sub.run()
        mock_sub.run.assert_called()
        assert 1 == 1
"""
        smells = audit_file_smells("test_sub.py", content=code)
        self.assertTrue(any(s.rule_id == SmellType.ZERO_STATE_TAUTOLOGY.value for s in smells))

    def test_boundary_adapter_waives_mock_only_calls(self):
        # A boundary adapter asserting only mock interactions is waived under Route A domain injection
        code = """
import subprocess
import unittest
from unittest.mock import MagicMock

class TestSubprocessAdapter(unittest.TestCase):
    def test_run_cmd(self):
        mock_sub = MagicMock()
        mock_sub.run()
        mock_sub.run.assert_called()
"""
        smells = audit_file_smells("test_sub.py", content=code)
        self.assertFalse(any(s.rule_id == SmellType.ZERO_STATE_TAUTOLOGY.value for s in smells))

    def test_mock_only_waived_for_adapter_boundary(self):
        """Route A contract: Mock-only tests in adapter classes or files with adapter names/decorators are waived."""
        # 1. File name containing Adapter
        code_file = """
import unittest
from unittest.mock import MagicMock

class NetworkTest(unittest.TestCase):
    def test_network_dispatch(self):
        mock = MagicMock()
        mock.send()
        mock.assert_called_once()
"""
        issues_file = audit_file_smells("test_network_adapter.py", content=code_file)
        self.assertEqual(len(issues_file), 0)

        # 2. Class name containing Socket / Docker / Client / Process
        code_client = """
import unittest
from unittest.mock import MagicMock

class DockerContainerTest(unittest.TestCase):
    def test_docker_call(self):
        mock = MagicMock()
        mock.start()
        mock.assert_called_once()
"""
        issues_client = audit_file_smells("test_docker.py", content=code_client)
        self.assertEqual(len(issues_client), 0)

        # 3. Decorator @mock_network or @adapter_boundary
        code_dec = """
import unittest
from unittest.mock import MagicMock

class DecoratedTest(unittest.TestCase):
    @mock_network
    def test_call(self):
        mock = MagicMock()
        mock.ping()
        mock.assert_called_once()
"""
        issues_dec = audit_file_smells("test_api.py", content=code_dec)
        self.assertEqual(len(issues_dec), 0)


class TestPragmaSuppression(unittest.TestCase):
    """Tests inline and function-level '# agyis: no-smell <reason>' escape pragmas."""

    def test_inline_no_smell_suppresses_tautology(self):
        code = """
import unittest
from unittest.mock import MagicMock

class TestUserService(unittest.TestCase):
    # agyis: no-smell intentional tautology for harness verification
    def test_mock_only(self):
        m = MagicMock()
        m.act()
        m.act.assert_called_once()
"""
        smells = audit_file_smells("test_sample.py", content=code)
        self.assertEqual(len(smells), 0)

    def test_rule_specific_no_smell_suppresses_matching_rule(self):
        code = """
import unittest
from unittest.mock import MagicMock

class TestUserService(unittest.TestCase):
    def test_mock_only(self):
        m = MagicMock()
        m.act()
        m.act.assert_called_once()  # agyis: no-smell SM001 intentional
"""
        smells = audit_file_smells("test_sample.py", content=code)
        self.assertEqual(len(smells), 0)

    def test_rule_specific_no_smell_does_not_suppress_other_rules(self):
        code = """
import unittest
from unittest.mock import MagicMock

class TestUserService(unittest.TestCase):
    # agyis: no-smell SM003 wrong rule specified
    def test_mock_only(self):
        m = MagicMock()
        m.act()
        m.act.assert_called_once()
"""
        smells = audit_file_smells("test_sample.py", content=code)
        self.assertEqual(len(smells), 1)
        self.assertEqual(smells[0].rule_id, SmellType.ZERO_STATE_TAUTOLOGY.value)

    def test_ts_js_comment_no_smell_suppresses(self):
        code = """
describe('Legacy', () => {
    // agyis: no-smell legacy component test
    it('calls directly', () => {
        const vdom = Header({ title: 'test' });
        expect(vdom).toBeDefined();
    });
});
"""
        smells = audit_file_smells("Header.test.tsx", content=code)
        direct_call = [s for s in smells if s.rule_id == SmellType.DIRECT_COMPONENT_CALL.value]
        self.assertEqual(len(direct_call), 0)


class TestCLIDoctorIntegration(unittest.TestCase):
    """Tests CLI integration and JSON serialization."""

    def test_cli_parser_recognizes_anti_synthetic_flags(self):
        parser = build_parser()
        args = parser.parse_args(["doctor", "--anti-synthetic", "--test-path", "tests/"])
        self.assertEqual(args.subcommand, "doctor")
        self.assertTrue(args.anti_synthetic)
        self.assertEqual(str(args.test_path), "tests")

    def test_run_anti_synthetic_doctor_clean_returns_zero(self):
        with tempfile.TemporaryDirectory() as td:
            clean_file = Path(td) / "test_clean.py"
            clean_file.write_text(
                "import unittest\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(1 + 1, 2)\n",
                encoding="utf-8",
            )
            with patch("sys.stdout", new_callable=io.StringIO):
                ret = run_anti_synthetic_doctor(target_path=clean_file)
            self.assertEqual(ret, 0)

    def test_run_anti_synthetic_doctor_fails_on_hard_rejection(self):
        with tempfile.TemporaryDirectory() as td:
            bad_file = Path(td) / "test_bad.py"
            bad_file.write_text(
                "from unittest.mock import MagicMock\ndef test_bad():\n    m = MagicMock()\n    m.call()\n    m.call.assert_called()\n",
                encoding="utf-8",
            )
            with patch("sys.stdout", new_callable=io.StringIO):
                ret = run_anti_synthetic_doctor(target_path=bad_file)
            self.assertEqual(ret, 1)

    def test_run_anti_synthetic_doctor_json_output(self):
        with tempfile.TemporaryDirectory() as td:
            clean_file = Path(td) / "test_clean.py"
            clean_file.write_text(
                "import unittest\nclass T(unittest.TestCase):\n    def test_pass(self):\n        self.assertEqual(1 + 1, 2)\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                ret = run_anti_synthetic_doctor(target_path=clean_file, as_json=True)
            self.assertEqual(ret, 0)
            data = json.loads(stdout.getvalue())
            self.assertIn("summary", data)
            self.assertTrue(data["summary"]["passed"])
            self.assertEqual(data["summary"]["hard_rejections_count"], 0)

    def test_cmd_doctor_delegates_to_anti_synthetic(self):
        with tempfile.TemporaryDirectory() as td:
            clean_file = Path(td) / "test_clean.py"
            clean_file.write_text(
                "def test_clean():\n    assert 2 * 2 == 4\n",
                encoding="utf-8",
            )
            parser = build_parser()
            args = parser.parse_args(["doctor", "--anti-synthetic", "--test-path", str(clean_file), "--json"])
            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                code = cmd_doctor(args)
            self.assertEqual(code, 0)
            data = json.loads(stdout.getvalue())
            self.assertTrue(data["summary"]["passed"])


class TestPerformanceBenchmark(unittest.TestCase):
    """Verifies sub-second execution contract (<1.0s)."""

    def test_sub_second_audit_latency_on_large_test_suite(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            # Generate 40 simulated test files
            for i in range(40):
                f = td_path / f"test_module_{i}.py"
                f.write_text(
                    f"""
import unittest
from unittest.mock import MagicMock

class TestModule{i}(unittest.TestCase):
    def test_operation_{i}(self):
        mock = MagicMock()
        mock.do_work.return_value = "done_{i}"
        res = mock.do_work()
        mock.do_work.assert_called_once()
        self.assertEqual(res, "done_{i}")
""",
                    encoding="utf-8",
                )

            start = time.perf_counter()
            report = audit_workspace_test_smells(target_path=td_path)
            duration = time.perf_counter() - start

            self.assertEqual(report.scanned_files, 40)
            self.assertEqual(report.scanned_tests, 40)
            self.assertTrue(report.passed)
            # Strict sub-second assertion: must complete in <0.5s for 40 files
            self.assertLess(
                duration,
                0.5,
                f"AST smell linter took {duration:.4f}s for 40 files, exceeding sub-second benchmark!",
            )


class TestSM001Remediations(unittest.TestCase):
    """
    Verifies SM001 edge-case remediations:
    - Trivial assertion filtering (assertTrue(True), assert True, assert 1 == 1, assertEqual(1, 1))
    - Recognition of len(m.mock_calls) and m.call_args as mock assertions
    - Inclusion of assertIsInstance and assertNotIsInstance in state assertions catalog
    - Inclusion of assert_awaited* in AsyncMock assertion catalog
    """

    def test_sm001_trivial_assert_true_does_not_mask_pure_mock(self):
        code = """
import unittest
from unittest.mock import MagicMock

class TestTrivial(unittest.TestCase):
    def test_evasion(self):
        m = MagicMock()
        m.action()
        m.action.assert_called_once()
        self.assertTrue(True)
"""
        smells = audit_file_smells("test_trivial.py", content=code)
        sm001 = [s for s in smells if s.rule_id == SmellType.ZERO_STATE_TAUTOLOGY.value]
        self.assertEqual(len(sm001), 1)

    def test_sm001_trivial_assert_equals_constant_does_not_mask_pure_mock(self):
        code = """
import unittest
from unittest.mock import MagicMock

class TestTrivial(unittest.TestCase):
    def test_evasion(self):
        m = MagicMock()
        m.action()
        m.action.assert_called_once()
        self.assertEqual(1, 1)
        assert True
        assert 42 == 42
"""
        smells = audit_file_smells("test_trivial.py", content=code)
        sm001 = [s for s in smells if s.rule_id == SmellType.ZERO_STATE_TAUTOLOGY.value]
        self.assertEqual(len(sm001), 1)

    def test_sm001_len_mock_calls_counts_as_mock_assertion(self):
        code = """
import unittest
from unittest.mock import MagicMock

class TestMockInspection(unittest.TestCase):
    def test_inspect_calls(self):
        m = MagicMock()
        m.action()
        self.assertEqual(len(m.mock_calls), 1)
"""
        smells = audit_file_smells("test_mock_calls.py", content=code)
        sm001 = [s for s in smells if s.rule_id == SmellType.ZERO_STATE_TAUTOLOGY.value]
        self.assertEqual(len(sm001), 1)

    def test_sm001_mock_call_args_counts_as_mock_assertion(self):
        code = """
import unittest
from unittest.mock import MagicMock

class TestMockInspection(unittest.TestCase):
    def test_inspect_args(self):
        m = MagicMock()
        m.action(42)
        self.assertIsNotNone(m.call_args)
"""
        smells = audit_file_smells("test_call_args.py", content=code)
        sm001 = [s for s in smells if s.rule_id == SmellType.ZERO_STATE_TAUTOLOGY.value]
        self.assertEqual(len(sm001), 1)

    def test_sm001_assert_is_instance_counts_as_state_assertion(self):
        code = """
import unittest
from unittest.mock import MagicMock

class TestValidState(unittest.TestCase):
    def test_instance_check(self):
        m = MagicMock()
        m.action.assert_called_once()
        res = {"status": "ok"}
        self.assertIsInstance(res, dict)
        self.assertNotIsInstance(res, list)
"""
        smells = audit_file_smells("test_state.py", content=code)
        sm001 = [s for s in smells if s.rule_id == SmellType.ZERO_STATE_TAUTOLOGY.value]
        self.assertEqual(len(sm001), 0)

    def test_sm001_async_mock_assert_awaited_triggers_sm001(self):
        code = """
import unittest
from unittest.mock import AsyncMock

class TestAsync(unittest.IsolatedAsyncioTestCase):
    async def test_async_action(self):
        m = AsyncMock()
        await m.execute()
        m.execute.assert_awaited_once()
"""
        smells = audit_file_smells("test_async.py", content=code)
        sm001 = [s for s in smells if s.rule_id == SmellType.ZERO_STATE_TAUTOLOGY.value]
        self.assertEqual(len(sm001), 1)


class TestSM005FunctionLevelIsolation(unittest.TestCase):
    """
    Verifies SM005 boundary exemption scoping:
    File-level boundary module imports must NOT exempt unrelated test functions
    in the same file.
    """

    def test_sm005_boundary_module_isolated_to_calling_function(self):
        code = """
import subprocess
import unittest
from unittest.mock import MagicMock

class TestMixedFile(unittest.TestCase):
    def test_boundary_exercised(self):
        # Exercises subprocess -> exempt from SM005
        m1 = MagicMock()
        m2 = MagicMock()
        m3 = MagicMock()
        m1.return_value = 1
        m2.return_value = 2
        m3.return_value = 3
        m1.assert_called()
        res = subprocess.run(["echo", "hello"])
        self.assertEqual(res, 0)

    def test_business_logic_only(self):
        # High mock density, 0 boundary calls -> flagged with SM005 warning
        m1 = MagicMock()
        m2 = MagicMock()
        m3 = MagicMock()
        m1.return_value = 1
        m2.return_value = 2
        m3.return_value = 3
        m1.assert_called()
        self.assertEqual(len([1]), 1)
"""
        smells = audit_file_smells("test_mixed.py", content=code)
        sm005 = [s for s in smells if s.rule_id == SmellType.MOCK_DENSITY_WARNING.value]
        self.assertEqual(len(sm005), 1)
        self.assertEqual(sm005[0].test_name, "test_business_logic_only")


class TestTSJSScannerAndSM002(unittest.TestCase):
    """
    Verifies TS/JS test block regex expansions and SM002 static method exclusions.
    """

    def test_ts_js_scanner_supports_function_expressions_and_modifiers(self):
        code = """
describe('Full Suite', () => {
    it('standard function', function() {
        const m = vi.fn();
        m();
        expect(m).toHaveBeenCalled();
    });

    test.only('async function', async function(done) {
        const m = vi.fn();
        m();
        expect(m).toHaveBeenCalled();
    });

    test.each([[1, 2]])('each test', (a, b) => {
        const m = vi.fn();
        m();
        expect(m).toHaveBeenCalled();
    });
});
"""
        smells = audit_file_smells("test_suite.ts", content=code)
        sm001 = [s for s in smells if s.rule_id == SmellType.ZERO_STATE_TAUTOLOGY.value]
        self.assertEqual(len(sm001), 3)

    def test_sm002_excludes_static_class_methods(self):
        code = """
describe('Static Calls', () => {
    it('uses static class factory methods', () => {
        const client = ApiClient.Connect();
        const res = Result.Ok(42);
        const now = DateTime.Now();
        expect(client).toBeDefined();
        expect(res).toBeDefined();
        expect(now).toBeDefined();
    });
});
"""
        smells = audit_file_smells("test_static.ts", content=code)
        sm002 = [s for s in smells if s.rule_id == SmellType.DIRECT_COMPONENT_CALL.value]
        self.assertEqual(len(sm002), 0)

    def test_sm002_still_flags_direct_component_call(self):
        code = """
describe('Component Calls', () => {
    it('invokes component directly', () => {
        const comp = UserProfileCard({ userId: 'u1' });
        expect(comp).toBeDefined();
    });
});
"""
        smells = audit_file_smells("test_comp.tsx", content=code)
        sm002 = [s for s in smells if s.rule_id == SmellType.DIRECT_COMPONENT_CALL.value]
        self.assertEqual(len(sm002), 1)


class TestSM003FakeVRTHardening(unittest.TestCase):
    """
    Verifies SM003 detection hardening:
    - os.stat().st_size > 0
    - Pathlib division: (Path() / "screen.png").exists()
    - Chained resolve: Path("screen.png").resolve().exists()
    - Bare word 'difference' does not suppress SM003
    - Authentic VRT diff call suppresses SM003
    """

    def test_sm003_catches_os_stat_st_size(self):
        code = """
import os
import unittest

class TestUI(unittest.TestCase):
    def test_vrt_stat(self):
        self.assertTrue(os.stat('artifacts/screenshot.png').st_size > 0)
"""
        smells = audit_file_smells("test_vrt.py", content=code)
        sm003 = [s for s in smells if s.rule_id == SmellType.FAKE_VRT.value]
        self.assertEqual(len(sm003), 1)

    def test_sm003_catches_path_division(self):
        code = """
from pathlib import Path
import unittest

class TestUI(unittest.TestCase):
    def test_vrt_div(self):
        img = Path("out") / "screen.png"
        self.assertTrue(img.exists())
"""
        smells = audit_file_smells("test_vrt.py", content=code)
        sm003 = [s for s in smells if s.rule_id == SmellType.FAKE_VRT.value]
        self.assertEqual(len(sm003), 1)

    def test_sm003_catches_path_resolve_exists(self):
        code = """
from pathlib import Path
import unittest

class TestUI(unittest.TestCase):
    def test_vrt_resolve(self):
        assert Path("screen.png").resolve().exists()
"""
        smells = audit_file_smells("test_vrt.py", content=code)
        sm003 = [s for s in smells if s.rule_id == SmellType.FAKE_VRT.value]
        self.assertEqual(len(sm003), 1)

    def test_sm003_bare_word_difference_does_not_suppress_sm003(self):
        code = """
import os
import unittest

class TestUI(unittest.TestCase):
    def test_fake_vrt_with_diff_var(self):
        difference = 42
        # calculate difference
        self.assertTrue(os.path.exists("screenshot.png"))
"""
        smells = audit_file_smells("test_vrt.py", content=code)
        sm003 = [s for s in smells if s.rule_id == SmellType.FAKE_VRT.value]
        self.assertEqual(len(sm003), 1)

    def test_sm003_genuine_vrt_diff_call_suppresses_sm003(self):
        code = """
import os
import unittest

class TestUI(unittest.TestCase):
    def test_real_vrt(self):
        self.assertTrue(os.path.exists("screenshot.png"))
        diff = pixelmatch(img1, img2)
        self.assertEqual(diff, 0)
"""
        smells = audit_file_smells("test_vrt.py", content=code)
        sm003 = [s for s in smells if s.rule_id == SmellType.FAKE_VRT.value]
        self.assertEqual(len(sm003), 0)


class TestSM004AndPragmasAndCLI(unittest.TestCase):
    """
    Verifies SM004 echo assertion scalar filtering and nested traversal,
    strict pragma parsing, and CLI non-existent path validation.
    """

    def test_sm004_boolean_and_integer_returns_do_not_warn(self):
        code = """
import unittest
from unittest.mock import MagicMock

class TestScalars(unittest.TestCase):
    def test_bool_and_int(self):
        m = MagicMock()
        m.get_flag.return_value = True
        m.get_count.return_value = 0
        res_flag = m.get_flag()
        res_count = m.get_count()
        self.assertEqual(res_flag, True)
        self.assertEqual(res_count, 0)
"""
        smells = audit_file_smells("test_scalars.py", content=code)
        sm004 = [s for s in smells if s.rule_id == SmellType.ECHO_ASSERTION.value]
        self.assertEqual(len(sm004), 0)

    def test_sm004_nested_dict_and_list_traversal_warns(self):
        code = """
import unittest
from unittest.mock import MagicMock

class TestNested(unittest.TestCase):
    def test_nested_dict(self):
        m = MagicMock()
        m.get_user.return_value = {"data": {"id": "usr_99"}}
        res = m.get_user()
        self.assertEqual(res["data"]["id"], "usr_99")

    def test_nested_list(self):
        m = MagicMock()
        m.get_items.return_value = [{"id": "item_123"}]
        res = m.get_items()
        self.assertEqual(res[0]["id"], "item_123")
"""
        smells = audit_file_smells("test_nested.py", content=code)
        sm004 = [s for s in smells if s.rule_id == SmellType.ECHO_ASSERTION.value]
        self.assertEqual(len(sm004), 2)

    def test_ts_js_prettier_multiline_echo_warns(self):
        code = """
describe('Prettier Echo', () => {
    it('detects multiline return echo', async () => {
        const fetchUser = vi.fn().mockResolvedValue({
            id: 'usr_abc',
            name: 'Alice'
        });
        const res = await fetchUser();
        expect(res.id).toBe('usr_abc');
    });
});
"""
        smells = audit_file_smells("test_prettier.ts", content=code)
        sm004 = [s for s in smells if s.rule_id == SmellType.ECHO_ASSERTION.value]
        self.assertEqual(len(sm004), 1)

    def test_pragma_english_words_smoke_and_small_waive_all(self):
        code = """
import unittest
from unittest.mock import MagicMock

class TestPragma(unittest.TestCase):
    # agyis: no-smell Smoke test only
    def test_smoke(self):
        m = MagicMock()
        m.run()
        m.run.assert_called_once()
"""
        smells = audit_file_smells("test_pragma.py", content=code)
        self.assertEqual(len(smells), 0)

    def test_pragma_malformed_rule_does_not_silently_waive(self):
        code = """
import unittest
from unittest.mock import MagicMock

class TestPragma(unittest.TestCase):
    # agyis: no-smell SM-001 typo in rule
    def test_typo(self):
        m = MagicMock()
        m.run()
        m.run.assert_called_once()
"""
        smells = audit_file_smells("test_typo.py", content=code)
        sm001 = [s for s in smells if s.rule_id == SmellType.ZERO_STATE_TAUTOLOGY.value]
        self.assertEqual(len(sm001), 1)

    def test_cli_nonexistent_test_path_exits_code_1(self):
        exit_code = run_anti_synthetic_doctor(target_path="/tmp/nonexistent_path_42")
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
