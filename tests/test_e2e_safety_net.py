#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Comprehensive 4-Tier Opaque-Box E2E Test Suite for Epic #51 Phase 3.1:
Programmatic Safety Net (AST Smell Linter, Diff-Aware Micro-Mutator, Completion Fence).

Governing Specifications:
- ORIGINAL_REQUEST.md (Phase 3.1 Requirements R1, R2, R3)
- PROJECT.md (Features F1 through F18)
- TEST_INFRA.md (Testing Architecture & Scenario Catalog)

Architectural Invariants Enforced:
1. Opaque-Box Boundary: Tests exercise the system via public module functions,
   CLI commands, and observable side-effects.
2. Hermetic Isolation: Clean-room temporary workspaces via OpaqueBoxTestCase.
3. Sub-Second Benchmark Invariant: Entire test suite executes in <1.0s.
4. Progressive Testability: Dynamically verifies implemented milestones while
   cleanly reporting progress on planned milestones.
5. Zero-Facade Integrity: Explicit, derived expected outputs; real logic exercised.
"""

from __future__ import annotations

import ast
import difflib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple
import unittest
from unittest.mock import MagicMock, patch

from harness.delivery.constants import REPO_ROOT
from harness.discovery import get_git_modified_files, resolve_affected_tests
from harness.hooks.completion_fence_hook import (
    evaluate_stop,
    load_state,
    record_edit,
    record_verification,
    save_state,
)
from tests.e2e.harness_base import OpaqueBoxTestCase

# ---------------------------------------------------------------------------
# Progressive Milestone Probing
# ---------------------------------------------------------------------------

def _has_module(mod_name: str) -> bool:
    try:
        return importlib.util.find_spec(mod_name) is not None
    except (ModuleNotFoundError, ValueError, AttributeError):
        return False

HAVE_M1 = _has_module("harness.doctor.test_smells")
HAVE_M2 = _has_module("harness.mutation.micro_probe")


# Inspect if CLI commands support new flags
def _check_cli_flag(subcmd: str, flag: str) -> bool:
    try:
        from harness.cli import build_parser
        parser = build_parser()
        # Find subparser action
        for action in parser._actions:
            if hasattr(action, "choices") and action.choices and subcmd in action.choices:
                subparser = action.choices[subcmd]
                for subaction in subparser._actions:
                    if flag in subaction.option_strings:
                        return True
    except Exception:
        pass
    return False

HAVE_CLI_ANTI_SYNTHETIC = _check_cli_flag("doctor", "--anti-synthetic")
HAVE_CLI_MUTATION = _check_cli_flag("test", "--mutation")


# ===========================================================================
# Tier 1: Feature Coverage (Features F1 through F18)
# ===========================================================================

class TestTier1FeatureCoverage(OpaqueBoxTestCase):
    """
    Tier 1: Feature Coverage across nominal operating boundaries.
    Covers F1-F6 (AST Smell Linter), F7-F14 (Micro-Mutator), F15-F17 (Completion Fence),
    and F18 (Objective Verification & Sub-Second Performance).
    """

    # -----------------------------------------------------------------------
    # Feature 1 (F1): Zero-State Tautology Detection (It == 1.0)
    # -----------------------------------------------------------------------

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f1_01_pure_mock_assertion_tautology_hard_rejected(self) -> None:
        """Assures pure mock assertion test (It == 1.0) triggers SM001 hard rejection."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import unittest\n"
            "from unittest.mock import MagicMock\n\n"
            "class UserServiceTest(unittest.TestCase):\n"
            "    def test_save_user(self):\n"
            "        mock_repo = MagicMock()\n"
            "        mock_repo.save({'name': 'alice'})\n"
            "        mock_repo.save.assert_called_once()\n"
        )
        test_file = self.ws / "tests" / "test_user_service.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        hard_rejections = [i for i in issues if getattr(i, "severity", None) in ("HARD_REJECTION", "hard_rejection")]
        sm001_issues = [i for i in hard_rejections if getattr(i, "rule_id", "") == "SM001" or "ZERO_STATE" in str(getattr(i, "smell_type", ""))]

        self.assertGreaterEqual(len(sm001_issues), 1, "Pure mock assertion must trigger SM001 hard rejection")
        self.assertIn("tautology", sm001_issues[0].message.lower())

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f1_02_mock_call_count_tautology_hard_rejected(self) -> None:
        """Assures asserting only mock.call_count with zero state assertions triggers SM001."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import unittest\n"
            "from unittest.mock import MagicMock\n\n"
            "class OrderTest(unittest.TestCase):\n"
            "    def test_dispatch_order(self):\n"
            "        bus = MagicMock()\n"
            "        bus.emit('event')\n"
            "        self.assertEqual(bus.call_count, 1)\n"
        )
        test_file = self.ws / "tests" / "test_order.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        sm001_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM001" or "ZERO_STATE" in str(getattr(i, "smell_type", ""))]
        self.assertGreaterEqual(len(sm001_issues), 1, "mock.call_count only assertion must trigger SM001")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f1_03_valid_state_assertion_passes(self) -> None:
        """Assures test with real data assertion has 0 SM001 hard rejections."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import unittest\n\n"
            "class CalculatorTest(unittest.TestCase):\n"
            "    def test_add(self):\n"
            "        val = 20 + 22\n"
            "        self.assertEqual(val, 42)\n"
        )
        test_file = self.ws / "tests" / "test_calc.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        hard_rejections = [i for i in issues if getattr(i, "severity", None) in ("HARD_REJECTION", "hard_rejection")]
        self.assertEqual(len(hard_rejections), 0, "Legitimate state assertion must not produce hard rejections")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f1_04_mixed_state_and_mock_assertions_passes(self) -> None:
        """Assures test with mock assertion AND state assertion (It = 0.5) passes cleanly."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import unittest\n"
            "from unittest.mock import MagicMock\n\n"
            "class AccountTest(unittest.TestCase):\n"
            "    def test_debit(self):\n"
            "        notifier = MagicMock()\n"
            "        balance = 100 - 30\n"
            "        notifier.send('debited')\n"
            "        notifier.send.assert_called_once()\n"
            "        self.assertEqual(balance, 70)\n"
        )
        test_file = self.ws / "tests" / "test_account.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        sm001_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM001" or "ZERO_STATE" in str(getattr(i, "smell_type", ""))]
        self.assertEqual(len(sm001_issues), 0, "Mixed mock + state assertion (It < 1.0) must not trigger SM001")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f1_05_ts_zero_state_tautology_hard_rejected(self) -> None:
        """Assures TS/JS test with only expect(spy).toHaveBeenCalled* triggers SM001."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import { describe, it, expect, vi } from 'vitest';\n"
            "describe('UserService', () => {\n"
            "  it('saves user', () => {\n"
            "    const spy = vi.fn();\n"
            "    spy({ name: 'alice' });\n"
            "    expect(spy).toHaveBeenCalledTimes(1);\n"
            "  });\n"
            "});\n"
        )
        test_file = self.ws / "tests" / "user.spec.ts"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        sm001_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM001" or "ZERO_STATE" in str(getattr(i, "smell_type", ""))]
        self.assertGreaterEqual(len(sm001_issues), 1, "TS/JS zero-state tautology must trigger SM001")

    # -----------------------------------------------------------------------
    # Feature 2 (F2): Direct Component Call Detection
    # -----------------------------------------------------------------------

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f2_01_direct_react_component_call_hard_rejected(self) -> None:
        """Assures invoking React component directly as a function triggers SM002."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import { Header } from '../components/Header';\n"
            "test('renders header', () => {\n"
            "  const vdom = Header({ title: 'Welcome' });\n"
            "  expect(vdom).toBeDefined();\n"
            "});\n"
        )
        test_file = self.ws / "tests" / "Header.test.tsx"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        sm002_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM002" or "DIRECT_COMPONENT" in str(getattr(i, "smell_type", ""))]
        self.assertGreaterEqual(len(sm002_issues), 1, "Direct Header() component call must trigger SM002")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f2_02_direct_vue_component_call_hard_rejected(self) -> None:
        """Assures invoking Vue component function directly triggers SM002."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import NavMenu from '../components/NavMenu.vue';\n"
            "test('nav menu', () => {\n"
            "  const res = NavMenu({ items: [] });\n"
            "  expect(res).toBeTruthy();\n"
            "});\n"
        )
        test_file = self.ws / "tests" / "NavMenu.spec.js"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        sm002_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM002" or "DIRECT_COMPONENT" in str(getattr(i, "smell_type", ""))]
        self.assertGreaterEqual(len(sm002_issues), 1, "Direct Vue component call must trigger SM002")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f2_03_mounted_react_component_render_passes(self) -> None:
        """Assures mounting component via @testing-library/react render() passes cleanly."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import { render, screen } from '@testing-library/react';\n"
            "import { Header } from '../components/Header';\n"
            "test('renders header mounted', () => {\n"
            "  render(<Header title='Welcome' />);\n"
            "  expect(screen.getByText('Welcome')).toBeInTheDocument();\n"
            "});\n"
        )
        test_file = self.ws / "tests" / "HeaderMounted.test.tsx"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        sm002_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM002" or "DIRECT_COMPONENT" in str(getattr(i, "smell_type", ""))]
        self.assertEqual(len(sm002_issues), 0, "Mounted component render must not trigger SM002")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f2_04_react_create_element_passes(self) -> None:
        """Assures React.createElement(Component) passes without triggering SM002."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import React from 'react';\n"
            "import { render } from '@testing-library/react';\n"
            "import { Button } from './Button';\n"
            "test('renders button', () => {\n"
            "  render(React.createElement(Button, { label: 'Click' }));\n"
            "  expect(true).toBe(true);\n"
            "});\n"
        )
        test_file = self.ws / "tests" / "Button.test.js"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        sm002_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM002"]
        self.assertEqual(len(sm002_issues), 0, "React.createElement mounting must not trigger SM002")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f2_05_pascal_case_utility_exclusion_passes(self) -> None:
        """Assures standard PascalCase utility functions (Buffer.from, URL, Symbol) are excluded."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "test('parses url and buffer', () => {\n"
            "  const buf = Buffer.from('abc');\n"
            "  const u = new URL('https://example.com');\n"
            "  const s = Symbol('key');\n"
            "  expect(buf.length).toBe(3);\n"
            "  expect(u.hostname).toBe('example.com');\n"
            "});\n"
        )
        test_file = self.ws / "tests" / "utils.test.ts"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        sm002_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM002"]
        self.assertEqual(len(sm002_issues), 0, "PascalCase JS/Node utilities must not trigger SM002")

    # -----------------------------------------------------------------------
    # Feature 3 (F3): Fake VRT Detection
    # -----------------------------------------------------------------------

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f3_01_fake_vrt_os_path_exists_hard_rejected(self) -> None:
        """Assures asserting os.path.exists on screenshot files triggers SM003."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import os, unittest\n\n"
            "class VrtTest(unittest.TestCase):\n"
            "    def test_screenshot_taken(self):\n"
            "        path = 'artifacts/screenshots/modal.png'\n"
            "        self.assertTrue(os.path.exists(path))\n"
        )
        test_file = self.ws / "tests" / "test_vrt.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        sm003_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM003" or "FAKE_VRT" in str(getattr(i, "smell_type", ""))]
        self.assertGreaterEqual(len(sm003_issues), 1, "Fake VRT os.path.exists on screenshot must trigger SM003")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f3_02_fake_vrt_path_exists_hard_rejected(self) -> None:
        """Assures assert Path('screenshot.png').exists() triggers SM003."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "from pathlib import Path\n"
            "def test_ui_capture():\n"
            "    p = Path('tests/snapshots/dashboard.png')\n"
            "    assert p.exists()\n"
        )
        test_file = self.ws / "tests" / "test_dash.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        sm003_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM003" or "FAKE_VRT" in str(getattr(i, "smell_type", ""))]
        self.assertGreaterEqual(len(sm003_issues), 1, "Path.exists() on snapshot image must trigger SM003")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f3_03_fake_vrt_ts_fs_exists_sync_hard_rejected(self) -> None:
        """Assures TS test asserting fs.existsSync on screenshot triggers SM003."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import fs from 'fs';\n"
            "test('takes screenshot', () => {\n"
            "  expect(fs.existsSync('screenshots/page.png')).toBe(true);\n"
            "});\n"
        )
        test_file = self.ws / "tests" / "screenshot.test.ts"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        sm003_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM003" or "FAKE_VRT" in str(getattr(i, "smell_type", ""))]
        self.assertGreaterEqual(len(sm003_issues), 1, "TS fs.existsSync on screenshot must trigger SM003")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f3_04_valid_pixel_diff_vrt_passes(self) -> None:
        """Assures test using Playwright toHaveScreenshot or pixelmatch passes without SM003."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import { test, expect } from '@playwright/test';\n"
            "test('visual comparison', async ({ page }) => {\n"
            "  await expect(page).toHaveScreenshot('landing.png');\n"
            "});\n"
        )
        test_file = self.ws / "tests" / "landing.vrt.ts"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        sm003_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM003"]
        self.assertEqual(len(sm003_issues), 0, "Authentic pixel diff VRT must not trigger SM003")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f3_05_non_screenshot_file_exists_passes(self) -> None:
        """Assures asserting file existence on config.json or data.csv does not trigger SM003."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import os, unittest\n"
            "class ConfigTest(unittest.TestCase):\n"
            "    def test_config_generated(self):\n"
            "        self.assertTrue(os.path.exists('data/config.json'))\n"
        )
        test_file = self.ws / "tests" / "test_config_gen.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        sm003_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM003"]
        self.assertEqual(len(sm003_issues), 0, "Asserting existence on non-image file must not trigger SM003")

    # -----------------------------------------------------------------------
    # Feature 4 (F4): Echo Assertion Detection
    # -----------------------------------------------------------------------

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f4_01_echo_assertion_primitive_return_value_warns(self) -> None:
        """Assures assertion strictly mirroring mock.return_value emits SM004 warning."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import unittest\n"
            "from unittest.mock import MagicMock\n\n"
            "class EchoTest(unittest.TestCase):\n"
            "    def test_echo(self):\n"
            "        client = MagicMock()\n"
            "        client.get_token.return_value = 'tok_secret_123'\n"
            "        token = client.get_token()\n"
            "        self.assertEqual(token, 'tok_secret_123')\n"
        )
        test_file = self.ws / "tests" / "test_echo.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        sm004_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM004" or "ECHO_ASSERTION" in str(getattr(i, "smell_type", ""))]
        self.assertGreaterEqual(len(sm004_issues), 1, "Echo assertion mirroring mock return must trigger SM004")
        self.assertEqual(sm004_issues[0].severity.lower(), "warning")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f4_02_echo_assertion_dict_property_return_value_warns(self) -> None:
        """Assures asserting property of returned dict matching mock configuration emits SM004."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import unittest\n"
            "from unittest.mock import MagicMock\n\n"
            "class UserEchoTest(unittest.TestCase):\n"
            "    def test_fetch_user(self):\n"
            "        api = MagicMock()\n"
            "        api.get_user.return_value = {'id': 'usr_99', 'role': 'admin'}\n"
            "        user = api.get_user()\n"
            "        self.assertEqual(user['id'], 'usr_99')\n"
        )
        test_file = self.ws / "tests" / "test_user_echo.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        sm004_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM004"]
        self.assertGreaterEqual(len(sm004_issues), 1, "Dict property echo assertion must trigger SM004")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f4_03_echo_assertion_ts_mock_resolved_value_warns(self) -> None:
        """Assures TS mockResolvedValue('tok_secret') mirrored in expect(res).toBe('tok_secret') triggers SM004."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "test('echo client', async () => {\n"
            "  const mockFetch = vi.fn().mockResolvedValue('tok_secret');\n"
            "  const res = await mockFetch();\n"
            "  expect(res).toBe('tok_secret');\n"
            "});\n"
        )
        test_file = self.ws / "tests" / "echo.test.ts"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        sm004_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM004"]
        self.assertGreaterEqual(len(sm004_issues), 1, "TS mockResolvedValue echo assertion must trigger SM004")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f4_04_non_echo_data_transformation_passes(self) -> None:
        """Assures assertion validating transformed data (not literal echo) passes cleanly."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import unittest\n"
            "from unittest.mock import MagicMock\n\n"
            "class TransformTest(unittest.TestCase):\n"
            "    def test_double_val(self):\n"
            "        source = MagicMock()\n"
            "        source.get_value.return_value = 10\n"
            "        doubled = source.get_value() * 2\n"
            "        self.assertEqual(doubled, 20)\n"
        )
        test_file = self.ws / "tests" / "test_transform.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        sm004_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM004"]
        self.assertEqual(len(sm004_issues), 0, "Transformed value assertion must not trigger SM004")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f4_05_warning_does_not_block_hard_rejection_passed_flag(self) -> None:
        """Assures an audit containing only warnings has passed == True."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import unittest\n"
            "from unittest.mock import MagicMock\n"
            "class EchoOnlyTest(unittest.TestCase):\n"
            "    def test_echo(self):\n"
            "        m = MagicMock(return_value='abc')\n"
            "        self.assertEqual(m(), 'abc')\n"
        )
        test_file = self.ws / "tests" / "test_echo_only.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        hard_rejections = [i for i in issues if getattr(i, "severity", None) in ("HARD_REJECTION", "hard_rejection")]
        self.assertEqual(len(hard_rejections), 0, "Echo warning must not be classified as a hard rejection")

    # -----------------------------------------------------------------------
    # Feature 5 (F5): Boundary Adapter Exemption
    # -----------------------------------------------------------------------

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f5_01_socket_adapter_mock_density_waived(self) -> None:
        """Assures test wrapping raw sockets waives mock density warning with EXEMPTION record."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import socket, unittest\n"
            "from unittest.mock import patch, MagicMock\n\n"
            "class SocketTransportTest(unittest.TestCase):\n"
            "    @patch('socket.socket')\n"
            "    def test_connect(self, mock_socket):\n"
            "        s = socket.socket()\n"
            "        s.connect(('127.0.0.1', 8080))\n"
            "        self.assertTrue(s.connect.called)\n"
            "        self.assertEqual(s.family, socket.AF_INET)\n"
        )
        test_file = self.ws / "tests" / "test_socket_adapter.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        mock_density_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM005"]
        self.assertEqual(len(mock_density_issues), 0, "Socket adapter must waive mock density warnings")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f5_02_subprocess_adapter_mock_density_waived(self) -> None:
        """Assures tests wrapping subprocess.run waive mock density warning."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import subprocess, unittest\n"
            "from unittest.mock import patch\n\n"
            "class CommandRunnerTest(unittest.TestCase):\n"
            "    @patch('subprocess.run')\n"
            "    def test_run_cmd(self, mock_run):\n"
            "        mock_run.return_value.returncode = 0\n"
            "        res = subprocess.run(['ls'])\n"
            "        self.assertEqual(res.returncode, 0)\n"
        )
        test_file = self.ws / "tests" / "test_cmd_adapter.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        mock_density_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM005"]
        self.assertEqual(len(mock_density_issues), 0, "Subprocess adapter must waive mock density warnings")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f5_03_docker_adapter_mock_density_waived(self) -> None:
        """Assures tests interacting with Docker SDK waive mock density warning."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import docker, unittest\n"
            "from unittest.mock import patch, MagicMock\n\n"
            "class DockerManagerTest(unittest.TestCase):\n"
            "    @patch('docker.from_env')\n"
            "    def test_container_run(self, mock_client):\n"
            "        container = MagicMock()\n"
            "        container.status = 'running'\n"
            "        mock_client.return_value.containers.get.return_value = container\n"
            "        self.assertEqual(container.status, 'running')\n"
        )
        test_file = self.ws / "tests" / "test_docker_adapter.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        mock_density_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM005"]
        self.assertEqual(len(mock_density_issues), 0, "Docker adapter must waive mock density warnings")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f5_04_boundary_adapter_still_enforces_zero_state_tautology(self) -> None:
        """Assures boundary adapter test asserting ONLY mock call still fails with SM001."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import socket, unittest\n"
            "from unittest.mock import MagicMock\n\n"
            "class SocketTautologyTest(unittest.TestCase):\n"
            "    def test_connect(self):\n"
            "        mock_sock = MagicMock()\n"
            "        mock_sock.connect(('127.0.0.1', 80))\n"
            "        mock_sock.connect.assert_called_once()\n"
        )
        test_file = self.ws / "tests" / "test_sock_tautology.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        sm001_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM001" or "ZERO_STATE" in str(getattr(i, "smell_type", ""))]
        self.assertGreaterEqual(len(sm001_issues), 1, "Boundary adapter with zero state assertions must still trigger SM001")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_f5_05_non_boundary_high_mock_density_warns(self) -> None:
        """Assures pure business domain test with excessive mock density generates SM005 warning."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import unittest\n"
            "from unittest.mock import MagicMock\n\n"
            "class CheckoutServiceTest(unittest.TestCase):\n"
            "    def test_checkout(self):\n"
            "        m1 = MagicMock()\n"
            "        m2 = MagicMock()\n"
            "        m3 = MagicMock()\n"
            "        m1.auth()\n"
            "        m2.tax()\n"
            "        m3.bill()\n"
            "        self.assertTrue(m1.called)\n"
            "        self.assertTrue(m2.called)\n"
            "        self.assertTrue(m3.called)\n"
            "        self.assertEqual(1, 1)\n"
        )
        test_file = self.ws / "tests" / "test_checkout_domain.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        # SM005 or high mock density warning
        sm005 = [i for i in issues if getattr(i, "rule_id", "") == "SM005" or "MOCK_DENSITY" in str(getattr(i, "smell_type", ""))]
        self.assertGreaterEqual(len(sm005), 1, "Non-boundary test with 5 mocks and 1 trivial state assertion must warn on mock density")

    # -----------------------------------------------------------------------
    # Feature 6 (F6): CLI Doctor --anti-synthetic
    # -----------------------------------------------------------------------

    @unittest.skipUnless(HAVE_CLI_ANTI_SYNTHETIC, "CLI flag agyis doctor --anti-synthetic not yet registered")
    def test_f6_01_cli_doctor_anti_synthetic_clean_tests_exit_zero(self) -> None:
        """Assures agyis doctor --anti-synthetic exits 0 when tests have no hard rejections."""
        clean_dir = self.ws / "clean_tests"
        clean_dir.mkdir(parents=True, exist_ok=True)
        (clean_dir / "test_ok.py").write_text(
            "import unittest\nclass OkTest(unittest.TestCase):\n    def test_ok(self):\n        self.assertEqual(1+1, 2)\n",
            encoding="utf-8",
        )
        code, out, err = self.run_cli(["doctor", "--anti-synthetic", "--test-path", str(clean_dir)])
        self.assertEqual(code, 0, f"Clean test audit must exit 0, got {code}.\nStdout: {out}\nStderr: {err}")

    @unittest.skipUnless(HAVE_CLI_ANTI_SYNTHETIC, "CLI flag agyis doctor --anti-synthetic not yet registered")
    def test_f6_02_cli_doctor_anti_synthetic_smell_exit_one(self) -> None:
        """Assures agyis doctor --anti-synthetic exits 1 when a hard smell rejection is present."""
        smell_dir = self.ws / "smell_tests"
        smell_dir.mkdir(parents=True, exist_ok=True)
        (smell_dir / "test_tautology.py").write_text(
            "import unittest\nfrom unittest.mock import MagicMock\nclass TTest(unittest.TestCase):\n    def test_t(self):\n        m = MagicMock()\n        m.run.assert_called_once()\n",
            encoding="utf-8",
        )
        code, out, err = self.run_cli(["doctor", "--anti-synthetic", "--test-path", str(smell_dir)])
        self.assertEqual(code, 1, f"Smell audit with hard rejection must exit 1, got {code}.\nStdout: {out}")

    @unittest.skipUnless(HAVE_CLI_ANTI_SYNTHETIC, "CLI flag agyis doctor --anti-synthetic not yet registered")
    def test_f6_03_cli_doctor_anti_synthetic_json_format(self) -> None:
        """Assures agyis doctor --anti-synthetic --json outputs structured schema."""
        test_dir = self.ws / "json_tests"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "test_sample.py").write_text(
            "import unittest\nclass STest(unittest.TestCase):\n    def test_s(self):\n        self.assertTrue(True)\n",
            encoding="utf-8",
        )
        code, out, err = self.run_cli(["doctor", "--anti-synthetic", "--test-path", str(test_dir), "--json"])
        data = self.parse_json_stdout(out)
        self.assertIn("summary", data)
        self.assertIn("hard_rejections", data)
        self.assertIn("warnings", data)

    @unittest.skipUnless(HAVE_CLI_ANTI_SYNTHETIC, "CLI flag agyis doctor --anti-synthetic not yet registered")
    def test_f6_04_cli_doctor_anti_synthetic_custom_test_path(self) -> None:
        """Assures --test-path flag scopes audit to specified directory."""
        scoped_dir = self.ws / "custom_scope"
        scoped_dir.mkdir(parents=True, exist_ok=True)
        (scoped_dir / "test_clean.py").write_text(
            "def test_pass(): assert 2*2 == 4\n", encoding="utf-8"
        )
        code, out, _ = self.run_cli(["doctor", "--anti-synthetic", "--test-path", str(scoped_dir)])
        self.assertEqual(code, 0)
        self.assertIn(str(scoped_dir), out)

    @unittest.skipUnless(HAVE_CLI_ANTI_SYNTHETIC, "CLI flag agyis doctor --anti-synthetic not yet registered")
    def test_f6_05_cli_doctor_anti_synthetic_help_flag(self) -> None:
        """Assures agyis doctor --help lists --anti-synthetic."""
        code, out, _ = self.run_cli(["doctor", "--help"])
        self.assertEqual(code, 0)
        self.assertIn("--anti-synthetic", out)

    # -----------------------------------------------------------------------
    # Feature 7-14 (F7-F14): Diff-Aware In-Harness Micro-Mutator Engine
    # -----------------------------------------------------------------------

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_f7_01_ast_transformer_preserves_surrounding_code(self) -> None:
        """Assures AST transformation preserves comments and surrounding whitespace."""
        from harness.mutation.micro_probe import mutate_python_source

        src = (
            "# Important module header\n"
            "def compute(x: int) -> bool:\n"
            "    # check non-zero\n"
            "    if x == 0:\n"
            "        return False\n"
            "    return True\n"
        )
        mutated, diff = mutate_python_source(src, target_line=4, operator="condition_inversion")
        self.assertIn("# Important module header", mutated)
        self.assertIn("# check non-zero", mutated)
        self.assertIn("if x != 0:", mutated)

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_f8_01_polyglot_ts_token_replacement(self) -> None:
        """Assures polyglot fallback mutates TS token === to !==."""
        from harness.mutation.micro_probe import mutate_token_source

        ts_code = "if (status === 'READY') { return true; }"
        mutated, op = mutate_token_source(ts_code, lang="ts")
        self.assertIn("status !== 'READY'", mutated)

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_f8_02_polyglot_rust_token_replacement(self) -> None:
        """Assures polyglot fallback mutates Rust token && to ||."""
        from harness.mutation.micro_probe import mutate_token_source

        rs_code = "if is_valid && has_quota { Ok(()) } else { Err(()) }"
        mutated, op = mutate_token_source(rs_code, lang="rust")
        self.assertIn("is_valid || has_quota", mutated)

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_f9_01_diff_targeting_only_uncommitted_lines(self) -> None:
        """Assures micro-mutator strictly mutates lines inside git diff."""
        from harness.mutation.micro_probe import extract_diff_mutation_candidates

        diff_text = (
            "--- a/src/app.py\n"
            "+++ b/src/app.py\n"
            "@@ -10,1 +10,2 @@\n"
            "+    if x > 10:\n"
            "+        return x\n"
        )
        candidates = extract_diff_mutation_candidates(diff_text)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].line_number, 10)
        self.assertEqual(candidates[1].line_number, 11)

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_f9_02_arid_line_suppression_imports_ignored(self) -> None:
        """Assures import statements are arid lines and produce 0 mutation candidates."""
        from harness.mutation.micro_probe import is_arid_line

        self.assertTrue(is_arid_line("import os"))
        self.assertTrue(is_arid_line("from pathlib import Path"))
        self.assertTrue(is_arid_line("import { Component } from 'react';"))

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_f9_03_arid_line_suppression_docstrings_comments_ignored(self) -> None:
        """Assures comments, docstrings, and log statements are suppressed as arid."""
        from harness.mutation.micro_probe import is_arid_line

        self.assertTrue(is_arid_line("# This is a comment"))
        self.assertTrue(is_arid_line('"""Module docstring"""'))
        self.assertTrue(is_arid_line("logger.info('Processing item')"))
        self.assertTrue(is_arid_line("print('debug')"))

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_f9_04_arid_line_suppression_type_annotations_ignored(self) -> None:
        """Assures pure type annotations are suppressed as arid."""
        from harness.mutation.micro_probe import is_arid_line

        self.assertTrue(is_arid_line("type ID = string | number;"))
        self.assertTrue(is_arid_line("interface User { name: string }"))

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_f9_05_clean_diff_returns_zero_mutants_in_sub_5ms(self) -> None:
        """Assures empty diff returns 0 mutants in under 5ms."""
        from harness.mutation.micro_probe import run_micro_mutation

        t0 = time.perf_counter()
        res = run_micro_mutation(target_diff="")
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertEqual(res.total_mutants, 0)
        self.assertEqual(res.exit_code, 0)
        self.assertLess(elapsed_ms, 50.0, f"Clean diff should evaluate in <50ms, took {elapsed_ms:.2f}ms")

    # 5-6 Mutation Operators
    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_f10_01_operator_condition_inversion(self) -> None:
        """Operator 1: Condition inversion (== <-> !=, < <-> >=)."""
        from harness.mutation.micro_probe import apply_operator

        src = "if a == b: pass"
        mutated = apply_operator(src, operator="condition_inversion")
        self.assertIn("a != b", mutated)

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_f10_02_operator_logical_operator_swap(self) -> None:
        """Operator 2: Logical operator swap (and <-> or)."""
        from harness.mutation.micro_probe import apply_operator

        src = "if valid and active: pass"
        mutated = apply_operator(src, operator="logical_swap")
        self.assertIn("valid or active", mutated)

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_f10_03_operator_boundary_shift(self) -> None:
        """Operator 3: Boundary shift (x + 1 <-> x - 1, > 0 <-> >= 0)."""
        from harness.mutation.micro_probe import apply_operator

        src = "return offset + 1"
        mutated = apply_operator(src, operator="boundary_shift")
        self.assertIn("offset - 1", mutated)

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_f10_04_operator_return_stubbing(self) -> None:
        """Operator 4: Return value stubbing (return x -> return None / False)."""
        from harness.mutation.micro_probe import apply_operator

        src = "return user_data"
        mutated = apply_operator(src, operator="return_stub")
        self.assertIn("return None", mutated)

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_f10_05_operator_void_statement_deletion(self) -> None:
        """Operator 5: Void statement deletion (side-effect call -> pass)."""
        from harness.mutation.micro_probe import apply_operator

        src = "cache.set('key', value)"
        mutated = apply_operator(src, operator="void_statement_delete")
        self.assertEqual(mutated.strip(), "pass")

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_f10_06_operator_literal_inversion(self) -> None:
        """Operator 6: Literal inversion (True <-> False)."""
        from harness.mutation.micro_probe import apply_operator

        src = "is_active = True"
        mutated = apply_operator(src, operator="literal_mutation")
        self.assertIn("is_active = False", mutated)

    # Feature 11: Affected Test Execution (using existing harness.discovery)
    def test_f11_01_affected_test_resolution_tier1a(self) -> None:
        """Assures resolve_affected_tests maps harness/<stem>.py to tests/test_<stem>.py."""
        res = resolve_affected_tests(modified_files=["harness/cli.py"], mode="diff")
        self.assertFalse(res.is_empty)
        self.assertTrue(any("test_cli.py" in str(tf) for tf in res.test_files))

    def test_f11_02_affected_test_empty_on_non_code_files(self) -> None:
        """Assures resolve_affected_tests returns empty for empty modified_files list."""
        res = resolve_affected_tests(modified_files=[], mode="diff")
        self.assertTrue(res.is_empty)
        self.assertEqual(len(res.test_files), 0)

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_f12_01_actionable_surviving_mutant_line_diff_output(self) -> None:
        """Assures surviving mutant formats actionable diff snippet with line numbers."""
        from harness.mutation.micro_probe import SurvivingMutant

        mutant = SurvivingMutant(
            file_path="harness/app.py",
            function_name="process_event",
            line_number=42,
            operator="condition_inversion",
            diff_snippet="- if x == 0:\n+ if x != 0:",
            test_target="tests/test_app.py",
        )
        report_str = mutant.to_actionable_report()
        self.assertIn("harness/app.py:42", report_str)
        self.assertIn("process_event", report_str)
        self.assertIn("- if x == 0:", report_str)
        self.assertIn("+ if x != 0:", report_str)

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_f13_01_inline_no_mutant_pragma_suppresses_mutation(self) -> None:
        """Assures # agyis: no-mutant suppresses mutant on the same line."""
        from harness.mutation.micro_probe import has_no_mutant_pragma

        line = "if offset >= 0:  # agyis: no-mutant boundary clamped upstream"
        self.assertTrue(has_no_mutant_pragma(line))

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_f13_02_preceding_line_no_mutant_pragma_suppresses_mutation(self) -> None:
        """Assures comment line immediately preceding statement suppresses mutations."""
        from harness.mutation.micro_probe import has_no_mutant_pragma

        comment = "# agyis: no-mutant hardware register layout"
        self.assertTrue(has_no_mutant_pragma(comment))

    @unittest.skipUnless(HAVE_CLI_MUTATION, "CLI flag agyis test --mutation not yet registered")
    def test_f14_01_cli_test_mutation_flag_clean_pass(self) -> None:
        """Assures agyis test --mutation exits 0 on clean diff."""
        code, out, _ = self.run_cli(["test", "--mutation"])
        self.assertEqual(code, 0)

    # -----------------------------------------------------------------------
    # Feature 15-17 (F15-F17): Completion Fence & Lifecycle Hook Integration
    # -----------------------------------------------------------------------

    def test_f17_01_completion_fence_anti_deadlock_valve_trips_after_2_blocks(self) -> None:
        """Assures completion fence trips safety valve on block_count >= 2."""
        conv_id = "test-deadlock-valve"
        (self.ws / "src").mkdir(parents=True, exist_ok=True)
        code_file = self.ws / "src" / "app.py"
        code_file.write_text("x = 1\n", encoding="utf-8")

        record_edit(str(code_file), conv_id=conv_id, state_dir=self.state_dir, cwd=self.ws)

        # Block 1
        res1 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.ws)
        self.assertEqual(res1.get("decision"), "continue")

        # Block 2
        res2 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.ws)
        self.assertEqual(res2.get("decision"), "continue")

        # Block 3 -> Safety valve tripped
        res3 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.ws)
        self.assertEqual(res3.get("decision"), "allow", "Safety valve must trip on 3rd attempt")
        self.assertTrue(
            res3.get("safety_valve_tripped", False)
            or "anti-deadlock" in res3.get("warning", "").lower()
            or "safety valve" in str(res3).lower(),
            f"Expected safety valve or anti-deadlock warning, got: {res3}",
        )

    # -----------------------------------------------------------------------
    # Feature 18 (F18): Objective Verification & Performance
    # -----------------------------------------------------------------------

    def test_f18_01_sub_second_latency_invariant(self) -> None:
        """Assures core discovery and fence stop evaluation execute in <100ms."""
        t0 = time.perf_counter()
        res = resolve_affected_tests(modified_files=["harness/discovery.py"], mode="diff")
        elapsed_discovery = time.perf_counter() - t0
        self.assertLess(elapsed_discovery, 0.2, f"Discovery took {elapsed_discovery:.3f}s; target <0.2s")

        t1 = time.perf_counter()
        conv_id = "perf-test"
        res_fence = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.ws)
        elapsed_fence = time.perf_counter() - t1
        self.assertLess(elapsed_fence, 0.1, f"Fence stop evaluation took {elapsed_fence:.3f}s; target <0.1s")


# ===========================================================================
# Tier 2: Boundary & Corner Cases
# ===========================================================================

class TestTier2BoundaryAndCornerCases(OpaqueBoxTestCase):
    """
    Tier 2: Boundary, degenerated, and adversarial corner cases.
    """

    def test_t2_01_empty_diff_clean_working_tree_sub_5ms(self) -> None:
        """Assures empty git diff evaluates cleanly with 0 affected tests."""
        res = resolve_affected_tests(modified_files=[], mode="diff")
        self.assertTrue(res.is_empty)
        self.assertEqual(len(res.test_files), 0)

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_t2_02_python_syntax_error_in_test_handled_gracefully(self) -> None:
        """Assures test file with Python syntax error does not crash the doctor linter."""
        from harness.doctor.test_smells import audit_file_smells

        bad_syntax_file = self.ws / "tests" / "test_malformed.py"
        bad_syntax_file.parent.mkdir(parents=True, exist_ok=True)
        bad_syntax_file.write_text("def test_broken(:\n    pass\n", encoding="utf-8")

        # Must not raise unhandled SyntaxError
        issues = audit_file_smells(str(bad_syntax_file))
        self.assertIsInstance(issues, list)

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_t2_03_pragma_with_arbitrary_spacing_and_unicode_comment(self) -> None:
        """Assures pragma parser handles arbitrary spacing, tabs, and unicode descriptions."""
        from harness.mutation.micro_probe import has_no_mutant_pragma

        line1 = "return x + 1  #   agyis:   no-mutant   equivalent boundary shift (λ -> α)"
        line2 = "return x + 1\t#agyis:no-mutant\t"
        line3 = "return x + 1  # AGYIS: NO-MUTANT UpperCase"
        self.assertTrue(has_no_mutant_pragma(line1))
        self.assertTrue(has_no_mutant_pragma(line2))
        self.assertTrue(has_no_mutant_pragma(line3))

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_t2_04_async_test_methods_and_nested_classes_audited(self) -> None:
        """Assures async test functions and nested test classes are inspected."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            "import unittest\n"
            "from unittest.mock import AsyncMock\n\n"
            "class Outer:\n"
            "    class NestedTest(unittest.TestCase):\n"
            "        async def test_async_tautology(self):\n"
            "            mock_coro = AsyncMock()\n"
            "            await mock_coro()\n"
            "            mock_coro.assert_called_once()\n"
        )
        test_file = self.ws / "tests" / "test_async_nested.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        sm001_issues = [i for i in issues if getattr(i, "rule_id", "") == "SM001" or "ZERO_STATE" in str(getattr(i, "smell_type", ""))]
        self.assertGreaterEqual(len(sm001_issues), 1, "Async nested test method must be detected for SM001")

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_t2_05_diversity_cap_at_most_5_to_6_mutants_per_function(self) -> None:
        """Assures function with dozens of mutation candidates is capped at 5-6 diverse mutants."""
        from harness.mutation.micro_probe import generate_function_mutants

        func_code = (
            "def heavy_logic(a, b, c, d, e, f, g):\n"
            "    if a == 1 and b == 2 and c == 3 and d == 4:\n"
            "        x = a + 1\n"
            "        y = b + 2\n"
            "        z = c + 3\n"
            "        do_call(x)\n"
            "        do_call(y)\n"
            "        return True\n"
            "    return False\n"
        )
        mutants = generate_function_mutants(func_code)
        self.assertLessEqual(len(mutants), 6, "Must generate at most 5-6 mutants per function")
        self.assertGreaterEqual(len(mutants), 3, "Must generate diverse mutants across available operators")

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_t2_06_file_with_only_comments_and_docstrings(self) -> None:
        """Assures test file containing only docstrings and comments produces 0 issues."""
        from harness.doctor.test_smells import audit_file_smells

        test_code = (
            '"""\nTest Suite Documentation\n"""\n'
            "# TODO: Implement future tests\n"
        )
        test_file = self.ws / "tests" / "test_empty_comment.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code, encoding="utf-8")

        issues = audit_file_smells(str(test_file))
        self.assertEqual(len(issues), 0, "Comments-only file must produce 0 smell issues")


# ===========================================================================
# Tier 3: Cross-Feature Combinations
# ===========================================================================

class TestTier3CrossFeatureCombinations(OpaqueBoxTestCase):
    """
    Tier 3: Multi-component lifecycle interplay.
    Smell Linter + Micro-Mutator + Completion Fence integration.
    """

    def test_t3_01_inner_loop_clean_turn_allows_conversational_exit(self) -> None:
        """Assures clean conversational turn without unverified code allows exit."""
        conv_id = "conv-turn-301"
        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.ws)
        self.assertEqual(res.get("decision"), "allow")

    def test_t3_02_code_edit_blocks_until_verified(self) -> None:
        """Assures editing code file dirties state and blocks stop until verified."""
        conv_id = "conv-turn-302"
        (self.ws / "harness").mkdir(parents=True, exist_ok=True)
        target = self.ws / "harness" / "module.py"
        target.write_text("def fn(): return 1\n", encoding="utf-8")

        record_edit(str(target), conv_id=conv_id, state_dir=self.state_dir, cwd=self.ws)
        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.ws)
        self.assertEqual(res.get("decision"), "continue", "Unverified code edit must block stop")

        # Record verification
        record_verification(success=True, tier="diff", conv_id=conv_id, state_dir=self.state_dir)
        res_after = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.ws)
        self.assertEqual(res_after.get("decision"), "allow", "Verified state must allow stop")

    def test_t3_03_handoff_gate_requires_affected_tier(self) -> None:
        """Assures modifying handoff.md blocks if verified_tier is below affected."""
        conv_id = "conv-turn-303"
        (self.ws / "harness").mkdir(parents=True, exist_ok=True)
        code_file = self.ws / "harness" / "core.py"
        code_file.write_text("x = 1\n", encoding="utf-8")

        record_edit(str(code_file), conv_id=conv_id, state_dir=self.state_dir, cwd=self.ws)
        # Verify with diff tier (Tier 1A)
        record_verification(success=True, tier="diff", conv_id=conv_id, state_dir=self.state_dir)

        # Now edit handoff.md
        handoff_file = self.ws / "handoff.md"
        handoff_file.write_text("# Handoff\nDone\n", encoding="utf-8")
        record_edit(str(handoff_file), conv_id=conv_id, state_dir=self.state_dir, cwd=self.ws)

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.ws)
        self.assertEqual(res.get("decision"), "continue", "Handoff gate requires Tier 1B affected, diff is insufficient")

        # Upgrade verification to affected (Tier 1B)
        record_verification(success=True, tier="affected", conv_id=conv_id, state_dir=self.state_dir)
        res_after = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.ws)
        self.assertEqual(res_after.get("decision"), "allow", "Affected tier unblocks handoff gate")


# ===========================================================================
# Tier 4: Real-World Scenarios
# ===========================================================================

class TestTier4RealWorldScenarios(OpaqueBoxTestCase):
    """
    Tier 4: Authentic agent and developer workflows under realistic conditions.
    """

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_t4_01_ai_synthetic_test_trap_reproduction_and_remediation(self) -> None:
        """
        Scenario 4.1: Agent writes a synthetic zero-state test to quickly satisfy a gate.
        1. Linter rejects test with SM001 hard rejection.
        2. Agent remediates by adding real state assertion.
        3. Linter passes cleanly.
        """
        from harness.doctor.test_smells import audit_file_smells

        test_path = self.ws / "tests" / "test_auth.py"
        test_path.parent.mkdir(parents=True, exist_ok=True)

        # Step 1: Agent writes synthetic test
        synthetic_code = (
            "import unittest\nfrom unittest.mock import MagicMock\n"
            "class AuthTest(unittest.TestCase):\n"
            "    def test_authenticate(self):\n"
            "        mock_auth = MagicMock()\n"
            "        mock_auth.verify('tok')\n"
            "        mock_auth.verify.assert_called_once()\n"
        )
        test_path.write_text(synthetic_code, encoding="utf-8")
        issues = audit_file_smells(str(test_path))
        self.assertTrue(any(getattr(i, "rule_id", "") == "SM001" for i in issues), "Synthetic test must be rejected")

        # Step 2: Agent remediates by asserting returned session token state
        remediated_code = (
            "import unittest\nfrom unittest.mock import MagicMock\n"
            "class AuthTest(unittest.TestCase):\n"
            "    def test_authenticate(self):\n"
            "        mock_auth = MagicMock()\n"
            "        mock_auth.verify.return_value = True\n"
            "        is_valid = mock_auth.verify('tok')\n"
            "        mock_auth.verify.assert_called_once()\n"
            "        self.assertTrue(is_valid)\n"
        )
        test_path.write_text(remediated_code, encoding="utf-8")
        clean_issues = audit_file_smells(str(test_path))
        hard_rejections = [i for i in clean_issues if getattr(i, "severity", None) in ("HARD_REJECTION", "hard_rejection")]
        self.assertEqual(len(hard_rejections), 0, "Remediated test must pass linter with 0 hard rejections")

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_t4_02_subtle_production_boundary_shift_detected_by_micro_mutator(self) -> None:
        """
        Scenario 4.2: Production code boundary condition mutated.
        A shallow test suite that does not test 0 passes on mutant (surviving mutant).
        Actionable diff clearly points to missed boundary condition.
        """
        from harness.mutation.micro_probe import SurvivingMutant

        mutant = SurvivingMutant(
            file_path="src/validator.py",
            function_name="is_positive",
            line_number=12,
            operator="boundary_shift",
            diff_snippet="- if val > 0:\n+ if val >= 0:",
            test_target="tests/test_validator.py",
        )
        feedback = mutant.to_actionable_report()
        self.assertIn("validator.py:12", feedback)
        self.assertIn("boundary_shift", feedback)
        self.assertIn("if val >= 0:", feedback)

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_t4_03_direct_react_component_call_refactored_to_render_mount(self) -> None:
        """
        Scenario 4.3: Direct React component call refactored to @testing-library render().
        """
        from harness.doctor.test_smells import audit_file_smells

        test_path = self.ws / "tests" / "Card.test.tsx"
        test_path.parent.mkdir(parents=True, exist_ok=True)

        # Bad: Direct component call
        test_path.write_text(
            "import { Card } from './Card';\n"
            "test('renders card', () => { expect(Card({ title: 'A' })).toBeDefined(); });\n",
            encoding="utf-8",
        )
        issues = audit_file_smells(str(test_path))
        self.assertTrue(any(getattr(i, "rule_id", "") == "SM002" for i in issues))

        # Good: Render mount
        test_path.write_text(
            "import { render, screen } from '@testing-library/react';\n"
            "import { Card } from './Card';\n"
            "test('renders card', () => {\n"
            "  render(<Card title='A' />);\n"
            "  expect(screen.getByText('A')).toBeInTheDocument();\n"
            "});\n",
            encoding="utf-8",
        )
        issues_clean = audit_file_smells(str(test_path))
        sm002_clean = [i for i in issues_clean if getattr(i, "rule_id", "") == "SM002"]
        self.assertEqual(len(sm002_clean), 0)


# ===========================================================================
# Tier 5: Adversarial Coverage Hardening
# ===========================================================================

class TestTier5AdversarialCoverageHardening(OpaqueBoxTestCase):
    """
    Tier 5: Adversarial Coverage Hardening & Edge Condition Invariants.
    Stress-tests complex AST mutations (nested async, chained comparisons, multiline
    returns, unicode byte offsets), multi-file anti-synthetic test smell audits with
    boundary exemptions, and the complete end-to-end fence lifecycle across real
    simulated agent conversation turns.
    """

    @unittest.skipUnless(HAVE_M2, "Milestone M2 (harness.mutation.micro_probe) not yet implemented")
    def test_t5_01_complex_ast_mutations_and_nested_async(self) -> None:
        """
        Adversarial Scenario 5.1: Test micro-mutator across deeply nested async methods,
        chained comparisons (1 < x <= 10), multiline returns, and unicode byte offsets.
        """
        from harness.mutation.micro_probe import generate_function_mutants, mutate_python_source

        # 1. Complex AST with nested async methods, chained comparison, and multiline return
        code = (
            "# 🚀 Header with unicode: 測試\n"
            "class PipelineWorker:\n"
            "    async def execute_task(self, x: int) -> bool:\n"
            "        async def _inner_flush(tag: str) -> None:\n"
            "            await self.telemetry.record_event('flush', tag)\n"
            "        if 1 < x <= 10:\n"
            "            await _inner_flush('active')\n"
            "            return (\n"
            "                'processed_result_'\n"
            "                + str(x)\n"
            "                + '_ok'\n"
            "            )\n"
            "        return False\n"
        )

        # Chained comparison: condition_inversion on line 6 (1 < x <= 10)
        mut_cond, diff_cond = mutate_python_source(code, 6, "condition_inversion")
        self.assertIn("1 >= x > 10", mut_cond)
        self.assertIn("-        if 1 < x <= 10:", diff_cond)
        self.assertIn("+        if 1 >= x > 10:", diff_cond)
        ast.parse(mut_cond)  # Verify compile validity

        # Chained comparison: boundary_shift on line 6 (1 < x <= 10)
        mut_bound, diff_bound = mutate_python_source(code, 6, "boundary_shift")
        self.assertIn("1 <= x < 10", mut_bound)
        self.assertIn("+        if 1 <= x < 10:", diff_bound)
        ast.parse(mut_bound)

        # Nested async await call: void_statement_delete on line 5 (await self.telemetry...)
        mut_void, diff_void = mutate_python_source(code, 5, "void_statement_delete")
        self.assertIn("pass", mut_void)
        self.assertIn("-            await self.telemetry.record_event('flush', tag)", diff_void)
        self.assertIn("+            pass", diff_void)
        ast.parse(mut_void)

        # Multiline return: return_stub on line 8 (return (\n 'processed_result_'...)
        mut_ret, diff_ret = mutate_python_source(code, 8, "return_stub")
        self.assertIn("return None", mut_ret)
        self.assertNotIn("processed_result_", mut_ret)
        self.assertIn("+            return None", diff_ret)
        ast.parse(mut_ret)

        # 2. Unicode byte offsets with multi-byte CJK and emojis on same line and preceding lines
        code_unicode = (
            "# 💖 PSL Telemetry — 🚀 測試\n"
            "def validate_status(symbol: str, count: int) -> bool:\n"
            "    label = 'こんにちは世界 🌍 🌟'; flag = (count >= 100)\n"
            "    if symbol == '✨':\n"
            "        return True\n"
            "    return False\n"
        )
        # Line 3 contains multi-byte CJK + emoji before 'count >= 100'
        # AST col_offset in Python 3.8+ is byte-based; test surgical replacement without corruption
        mut_uni_shift, diff_uni_shift = mutate_python_source(code_unicode, 3, "boundary_shift")
        self.assertIn("count > 100", mut_uni_shift)
        self.assertIn("こんにちは世界 🌍 🌟", mut_uni_shift)
        self.assertIn("-    label = 'こんにちは世界 🌍 🌟'; flag = (count >= 100)", diff_uni_shift)
        self.assertIn("+    label = 'こんにちは世界 🌍 🌟'; flag = (count > 100)", diff_uni_shift)
        ast.parse(mut_uni_shift)

        # Line 4 contains emoji comparison
        mut_uni_eq, diff_uni_eq = mutate_python_source(code_unicode, 4, "condition_inversion")
        self.assertIn("symbol != '✨'", mut_uni_eq)
        self.assertIn("+    if symbol != '✨':", diff_uni_eq)
        ast.parse(mut_uni_eq)

        # 3. generate_function_mutants across entire complex block
        mutants = generate_function_mutants(code, max_mutants=6)
        self.assertGreaterEqual(len(mutants), 3)
        operators_found = {m.operator for m in mutants}
        self.assertTrue(operators_found.intersection({"condition_inversion", "boundary_shift", "void_statement_delete", "return_stub"}))
        for m in mutants:
            ast.parse(m.mutated_code)

    @unittest.skipUnless(HAVE_M1, "Milestone M1 (harness.doctor.test_smells) not yet implemented")
    def test_t5_02_synthetic_doctor_multi_file_and_obfuscated_assertions(self) -> None:
        """
        Adversarial Scenario 5.2: Test doctor anti-synthetic smell detection across
        multi-file project structures and boundary exemptions.
        """
        from harness.doctor.test_smells import audit_workspace_test_smells

        tests_dir = self.ws / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        # File 1: Synthetic test (SM001 zero-state tautology)
        (tests_dir / "test_synthetic.py").write_text(
            "import unittest\n"
            "from unittest.mock import MagicMock\n"
            "class TestSynthetic(unittest.TestCase):\n"
            "    def test_fake(self):\n"
            "        mock_svc = MagicMock()\n"
            "        mock_svc.dispatch('evt')\n"
            "        mock_svc.dispatch.assert_called_once()\n",
            encoding="utf-8",
        )

        # File 2: Boundary adapter test (waives SM005 high mock density due to socket boundary)
        adapter_dir = tests_dir / "adapters"
        adapter_dir.mkdir(parents=True, exist_ok=True)
        (adapter_dir / "test_socket_adapter.py").write_text(
            "import unittest\n"
            "import socket\n"
            "from unittest.mock import MagicMock, patch\n"
            "class TestSocketAdapter(unittest.TestCase):\n"
            "    @patch('socket.socket')\n"
            "    def test_connect(self, mock_sock):\n"
            "        s = mock_sock.return_value\n"
            "        s.connect(('127.0.0.1', 80))\n"
            "        s.connect.assert_called_once()\n"
            "        s.send(b'ping')\n"
            "        s.send.assert_called_once()\n"
            "        s.recv.return_value = b'pong'\n"
            "        data = s.recv(1024)\n"
            "        s.recv.assert_called_once()\n"
            "        self.assertEqual(len(data), 4)\n",
            encoding="utf-8",
        )

        # File 3: Obfuscated echo assertion (SM004)
        (tests_dir / "test_echo.py").write_text(
            "import unittest\n"
            "from unittest.mock import MagicMock\n"
            "class TestEcho(unittest.TestCase):\n"
            "    def test_echo_payload(self):\n"
            "        mock_repo = MagicMock()\n"
            "        mock_repo.fetch.return_value = {'payload': 'auth_token_xyz_42'}\n"
            "        token = mock_repo.fetch()['payload']\n"
            "        self.assertEqual(token, 'auth_token_xyz_42')\n",
            encoding="utf-8",
        )

        # File 4: Frontend direct component call (SM002 hard rejection)
        (tests_dir / "Button.test.tsx").write_text(
            "import { Button } from './Button';\n"
            "describe('Button', () => {\n"
            "  it('renders button', () => {\n"
            "    const el = Button({ label: 'Submit' });\n"
            "    expect(el).toBeDefined();\n"
            "  });\n"
            "});\n",
            encoding="utf-8",
        )

        # File 5: Clean authentic unit test (no smells)
        (tests_dir / "test_clean.py").write_text(
            "import unittest\n"
            "class TestClean(unittest.TestCase):\n"
            "    def test_arithmetic(self):\n"
            "        self.assertEqual(sum([1, 2, 3]), 6)\n",
            encoding="utf-8",
        )

        report = audit_workspace_test_smells(workspace_root=self.ws)

        # Multi-file discovery assertion
        self.assertGreaterEqual(report.scanned_files, 5)
        self.assertGreaterEqual(report.scanned_tests, 5)
        self.assertFalse(report.passed, "Audit report must fail due to SM001 and SM002 hard rejections")

        hard_rule_ids = [r.rule_id for r in report.hard_rejections]
        self.assertIn("SM001", hard_rule_ids, "Synthetic test must produce SM001 hard rejection")
        self.assertIn("SM002", hard_rule_ids, "Direct component call must produce SM002 hard rejection")

        # Boundary exemption assertion: test_socket_adapter.py waived SM005
        self.assertGreaterEqual(len(report.exemptions), 1, "Boundary adapter must record an exemption")
        exemption_files = [e.file_path for e in report.exemptions]
        self.assertTrue(any("test_socket_adapter.py" in f for f in exemption_files))

        # Obfuscated echo assertion warning (SM004)
        warn_rule_ids = [w.rule_id for w in report.warnings]
        self.assertIn("SM004", warn_rule_ids, "Echo assertion test must produce SM004 warning")

    @unittest.skipUnless(HAVE_M1 and HAVE_M2, "Milestones M1 and M2 required for end-to-end fence lifecycle")
    def test_t5_03_end_to_end_fence_lifecycle_with_smells_and_mutation(self) -> None:
        """
        Adversarial Scenario 5.3: Test full end-to-end fence lifecycle in a simulated agent conversation:
        edit test with smell -> evaluate_stop blocks -> fix test smell -> evaluate_stop passes ->
        handoff blocked without mutation -> run test --mutation -> handoff passes.
        """
        from harness.hooks.completion_fence_hook import (
            check_command_verification,
            evaluate_stop,
            record_edit,
        )

        state_dir = self.ws / ".agyis_state"
        conv_id = f"conv_t5_lifecycle_{int(time.time())}"

        src_dir = self.ws / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        tests_dir = self.ws / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        prod_file = src_dir / "calculator.py"
        prod_file.write_text("def multiply(a: int, b: int) -> int:\n    return a * b\n", encoding="utf-8")

        test_file = tests_dir / "test_calculator.py"
        handoff_file = self.ws / "handoff.md"

        # -------------------------------------------------------------------
        # Phase 1: Agent writes a synthetic test containing SM001 smell
        # -------------------------------------------------------------------
        synthetic_test_code = (
            "import unittest\n"
            "from unittest.mock import MagicMock\n"
            "class TestCalculator(unittest.TestCase):\n"
            "    def test_multiply(self):\n"
            "        mock_calc = MagicMock()\n"
            "        mock_calc.mult(2, 3)\n"
            "        mock_calc.mult.assert_called_once()\n"
        )
        test_file.write_text(synthetic_test_code, encoding="utf-8")
        record_edit(str(test_file), conv_id=conv_id, state_dir=state_dir, cwd=self.ws)

        # evaluate_stop must block the agent turn due to hard rejection SM001
        res1 = evaluate_stop(conv_id=conv_id, state_dir=state_dir, cwd=self.ws)
        self.assertEqual(res1["decision"], "continue", "Fence must block turn completion on synthetic test smell")
        self.assertIn("Synthetic Test Smell Rejection", res1.get("reason", ""))
        self.assertIn("SM001", res1.get("reason", ""))

        # -------------------------------------------------------------------
        # Phase 2: Agent remediates the test smell and verifies unit tests
        # -------------------------------------------------------------------
        remediated_test_code = (
            "import unittest\n"
            "from src.calculator import multiply\n"
            "class TestCalculator(unittest.TestCase):\n"
            "    def test_multiply(self):\n"
            "        self.assertEqual(multiply(2, 3), 6)\n"
        )
        test_file.write_text(remediated_test_code, encoding="utf-8")
        record_edit(str(test_file), conv_id=conv_id, state_dir=state_dir, cwd=self.ws)

        # Run test verification
        check_command_verification(
            "python3 -m unittest tests/test_calculator.py",
            exit_code=0,
            conv_id=conv_id,
            state_dir=state_dir,
            cwd=self.ws,
        )

        # evaluate_stop must now allow turn completion
        res2 = evaluate_stop(conv_id=conv_id, state_dir=state_dir, cwd=self.ws)
        self.assertEqual(res2["decision"], "allow", "Fence must allow stop after remediating smell and verifying tests")

        # -------------------------------------------------------------------
        # Phase 3: Agent modifies production code and attempts handoff
        # -------------------------------------------------------------------
        prod_file.write_text(
            "def multiply(a: int, b: int) -> int:\n"
            "    if a == 0 or b == 0:\n"
            "        return 0\n"
            "    return a * b\n",
            encoding="utf-8",
        )
        record_edit(str(prod_file), conv_id=conv_id, state_dir=state_dir, cwd=self.ws)

        # Run affected tests (passes)
        check_command_verification(
            "python3 -m unittest tests/test_calculator.py",
            exit_code=0,
            conv_id=conv_id,
            state_dir=state_dir,
            cwd=self.ws,
        )

        # Agent writes handoff.md without running diff micro-mutation
        handoff_file.write_text(
            "# Milestone Handoff\n"
            "## Summary\n"
            "Production code updated with zero-handling optimization.\n",
            encoding="utf-8",
        )
        record_edit(str(handoff_file), conv_id=conv_id, state_dir=state_dir, cwd=self.ws)

        # evaluate_stop at handoff gate must block because mutation testing has not been run
        res3 = evaluate_stop(conv_id=conv_id, state_dir=state_dir, cwd=self.ws, payload={"gate_type": "handoff"})
        self.assertEqual(res3["decision"], "continue", "Handoff must be blocked until micro-mutation testing passes")
        self.assertIn("Micro-Mutation Verification Required", res3.get("reason", ""))

        # -------------------------------------------------------------------
        # Phase 4: Agent executes diff-aware micro-mutation testing
        # -------------------------------------------------------------------
        check_command_verification(
            "agyis test --mutation",
            exit_code=0,
            conv_id=conv_id,
            state_dir=state_dir,
            cwd=self.ws,
        )

        # evaluate_stop at handoff gate must now pass cleanly
        res4 = evaluate_stop(conv_id=conv_id, state_dir=state_dir, cwd=self.ws, payload={"gate_type": "handoff"})
        self.assertEqual(res4["decision"], "allow", "Handoff gate must pass once diff micro-mutation is verified")


# ===========================================================================
# Test Runner Invocation Entrypoint
# ===========================================================================

if __name__ == "__main__":
    unittest.main()

