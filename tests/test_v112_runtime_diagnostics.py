#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Hermetic verification suite for v1.1.2 Track 5 diagnostics & signal precision."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from harness.doctor.smell_models import SmellType
from harness.doctor.test_smells import audit_file_smells
from harness.runtime.aff import (
    _discover_workspace_files,
    audit_architectural_fitness,
    audit_structural_smells,
)
from harness.runtime.doctor import DEFAULT_MATRIX, run_doctor
from harness.runtime.engine_checks import check_package_engines, semver_satisfies
from harness.runtime.healing import heal_environment, provision_workspace_rea
from harness.runtime.hygiene_checks import check_node_script_hygiene


class TestEngineChecksAndPython314Uplift(unittest.TestCase):
    """Tests check_package_engines, semver comparators, matrix 3.14 uplift, and healing."""

    def test_semver_comparators(self) -> None:
        self.assertTrue(semver_satisfies("10.1.0", ">=10.0.0"))
        self.assertFalse(semver_satisfies("9.15.9", ">=10.0.0"))
        self.assertTrue(semver_satisfies("20.11.1", "^20.11.0"))
        self.assertFalse(semver_satisfies("21.0.0", "^20.11.0"))
        self.assertTrue(semver_satisfies("20.11.5", "~20.11.0"))
        self.assertFalse(semver_satisfies("20.12.0", "~20.11.0"))
        self.assertTrue(semver_satisfies("22.5.0", "^20.0.0 || >=22.0.0"))
        self.assertTrue(semver_satisfies("21.3.0", ">=20.0.0 <22.0.0"))
        self.assertFalse(semver_satisfies("22.0.0", ">=20.0.0 <22.0.0"))
        self.assertTrue(semver_satisfies("20.9.0", "20.0.0 - 22.0.0"))

    def test_check_package_engines_pnpm_mismatch_and_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            skipped = check_package_engines(ws)
            self.assertEqual(skipped["status"], "SKIPPED")

            (ws / "package.json").write_text(
                json.dumps({
                    "name": "purrfect-download-manager",
                    "engines": {"node": ">=20.0.0", "pnpm": ">=10.0.0"},
                    "packageManager": "pnpm@10.0.0",
                }),
                encoding="utf-8",
            )

            def mock_run(cmd, *args, **kwargs):
                tool_bin = str(cmd[0])
                if tool_bin.endswith("node"):
                    return MagicMock(returncode=0, stdout="v22.14.0\n", stderr="")
                if tool_bin.endswith("pnpm"):
                    return MagicMock(returncode=0, stdout="9.15.9\n", stderr="")
                return MagicMock(returncode=1, stdout="", stderr="")

            with patch("shutil.which", side_effect=lambda name: f"/usr/bin/{name}"), \
                 patch("subprocess.run", side_effect=mock_run):
                res = check_package_engines(ws)

            self.assertEqual(res["status"], "ERROR")
            self.assertTrue(any("9.15.9" in msg and ">=10.0.0" in msg for msg in res["issues"]))
            self.assertIn("corepack enable", res["fix_hints"])
            self.assertTrue(any("corepack prepare pnpm@10.0.0" in h for h in res["fix_hints"]))

            with patch("harness.runtime.doctor.check_cli_binary", return_value={"status": "OK", "agyis_status": "OK", "psl_details": {"status": "OK", "collision": False}}), \
                 patch("harness.runtime.doctor.check_tool", return_value={"name": "m", "binary": "m", "status": "OK", "path": "/bin/m", "version": "99.0.0", "min_version": "1.0.0", "is_shim": False, "shim_details": None, "is_collision": False, "collision_details": None, "spec": {}}), \
                 patch("harness.runtime.doctor.check_telemetry_daemon", return_value={"status": "OK", "message": "ok"}), \
                 patch("harness.runtime.doctor.check_database_port_conflicts", return_value={"status": "PASS"}), \
                 patch("harness.runtime.doctor.check_hooks_health", return_value={"status": "OK", "checked_hooks": []}), \
                 patch("harness.runtime.doctor.check_rea_tooling", return_value={"status": "optional_missing", "fast_path": True}), \
                 patch("shutil.which", side_effect=lambda name: f"/usr/bin/{name}"), \
                 patch("subprocess.run", side_effect=mock_run):
                audit = run_doctor(DEFAULT_MATRIX, workspace_root=ws)
            self.assertEqual(audit["package_engines"]["status"], "ERROR")
            self.assertGreaterEqual(audit["summary"]["warning"], 1)

    def test_matrix_and_healing_recommend_python_314(self) -> None:
        matrix = json.loads(DEFAULT_MATRIX.read_text(encoding="utf-8"))
        py_spec = matrix["tiers"]["tier_1_languages"]["tools"]["python"]
        self.assertEqual(py_spec["min_version"], "3.12.0")
        self.assertEqual(py_spec["recommended"], "3.14.0")
        self.assertEqual(py_spec["heal_strategy"]["install_command"], "uv python install 3.14")

        fake_audit = {
            "os_family": "linux",
            "tiers": {
                "tier_1_languages": {
                    "tools": [{
                        "name": "python",
                        "status": "WARNING",
                        "spec": py_spec,
                    }]
                }
            },
            "cli_binary": {"status": "OK"},
            "duplicate_agents": {"status": "OK"},
            "duplicate_skills": {"status": "PASS"},
            "node_script_hygiene": {"status": "OK"},
            "hooks_health": {"status": "OK"},
            "database_port_conflicts": {"status": "PASS"},
        }
        with patch("shutil.which", side_effect=lambda name: "/usr/bin/uv" if name == "uv" else None), \
             patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")) as mock_run:
            actions = heal_environment(fake_audit, DEFAULT_MATRIX)
        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args[0][0], ["/usr/bin/uv", "python", "install", "3.14"])
        self.assertTrue(any("3.14" in a for a in actions))


class TestReaGlobalSkipAndSmellPrecision(unittest.TestCase):
    """Tests provision_workspace_rea global skip, SM002 JS/PySide6 fixes, and AFF/Hygiene ignores."""

    def test_provision_workspace_rea_skips_when_globally_provisioned(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cfg = root / "config"
            ws = root / "ws"
            ws.mkdir()

            # 1. Not globally provisioned -> calls provision_rea_skill
            with patch("harness.runtime.healing.provision_rea_skill", return_value=ws / ".agents" / "skills" / "reverse-engineer-anything") as mock_prov:
                created, _ = provision_workspace_rea(ws, config_dir=cfg)
            self.assertTrue(created)
            mock_prov.assert_called_once()

            # 2. Standalone global skill present -> skips workspace symlink creation
            standalone_rea = cfg / "skills" / "reverse-engineer-anything"
            standalone_rea.mkdir(parents=True)
            (standalone_rea / "SKILL.md").write_text("# REA\n", encoding="utf-8")
            with patch("harness.runtime.healing.provision_rea_skill") as mock_prov:
                created2, _ = provision_workspace_rea(ws, config_dir=cfg)
            self.assertFalse(created2)
            mock_prov.assert_not_called()

            # 3. Plugin global skill present -> skips workspace symlink creation
            cfg2 = root / "config_plugin"
            plugin_rea = cfg2 / "plugins" / "agyis-harness" / "skills" / "reverse-engineer-anything"
            plugin_rea.mkdir(parents=True)
            (plugin_rea / "SKILL.md").write_text("# Plugin REA\n", encoding="utf-8")
            with patch("harness.runtime.healing.provision_rea_skill") as mock_prov:
                created3, _ = provision_workspace_rea(ws, config_dir=cfg2)
            self.assertFalse(created3)
            mock_prov.assert_not_called()

    def test_sm002_ignores_js_strings_templates_and_comments(self) -> None:
        code = """
import { render, screen } from '@testing-library/react';
describe('Strings and Comments', () => {
    it('does not trigger SM002 inside strings, template literals, or comments', () => {
        const a = "Header({ title: 'x' })";
        const b = 'Button({ onClick: true })';
        const c = `Multiline
            Modal({ open: true })
            and ${fmt('Card(1)')}
        `;
        // Sidebar({ collapsed: true })
        /* Footer({ year: 2026 }) */
        render(<Header />);
        expect(a + b + c).toContain('Header');
    });
});
"""
        smells = audit_file_smells("Strings.test.tsx", content=code)
        sm002 = [s for s in smells if s.rule_id == SmellType.DIRECT_COMPONENT_CALL.value]
        self.assertEqual(sm002, [])

        real_call = """
describe('Real Direct Call', () => {
    it('flags actual direct component call after comments', () => {
        // comment before call
        const el = Header({ title: 'Welcome' });
        expect(el).toBeDefined();
    });
});
"""
        smells2 = audit_file_smells("Real.test.tsx", content=real_call)
        sm002_2 = [s for s in smells2 if s.rule_id == SmellType.DIRECT_COMPONENT_CALL.value]
        self.assertEqual(len(sm002_2), 1)
        self.assertEqual(sm002_2[0].line_number, 5)

    def test_sm002_excludes_qt_and_pyside_classes(self) -> None:
        qt_code = """
from PySide6.QtCore import QObject
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, CustomQtWidget

def test_qml_component_instantiation():
    app = QApplication([])
    engine = QQmlApplicationEngine()
    comp = QQmlComponent(engine)
    win = QMainWindow()
    w = QWidget()
    custom = CustomQtWidget()
    assert comp is not None and win is not None and w is not None and app is not None and custom is not None
"""
        smells = audit_file_smells("test_qml_view.py", content=qt_code)
        sm002 = [s for s in smells if s.rule_id == SmellType.DIRECT_COMPONENT_CALL.value]
        self.assertEqual(sm002, [])

        react_py_code = """
def test_direct_component_call():
    out = NavHeaderComponent(props={"title": "hi"})
    assert out is not None
"""
        smells_bad = audit_file_smells("test_ui_py.py", content=react_py_code)
        sm002_bad = [s for s in smells_bad if s.rule_id == SmellType.DIRECT_COMPONENT_CALL.value]
        self.assertEqual(len(sm002_bad), 1)

    def test_aff_and_node_hygiene_ignore_static_dirs_min_js_and_gitignore(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            subprocess.run(["git", "init", "-b", "main"], cwd=ws, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            (ws / ".gitignore").write_text("generated/\nignored_script.js\n", encoding="utf-8")
            (ws / "package.json").write_text(json.dumps({"name": "esm-app", "type": "module"}), encoding="utf-8")
            (ws / "src").mkdir()
            (ws / "src" / "app.js").write_text("export const ok = 1;\n", encoding="utf-8")

            monolith_cjs = "const x = require('fs');\n" + ("const cache = new Map();\ncache.set('k', 1);\n" * 450)
            for rel_dir in ("public", "dist-scripts", "out", ".out", "coverage", "generated"):
                d = ws / rel_dir
                d.mkdir(parents=True, exist_ok=True)
                (d / "artifact.js").write_text(monolith_cjs, encoding="utf-8")

            (ws / "src" / "vendor.min.js").write_text(monolith_cjs, encoding="utf-8")
            (ws / "ignored_script.js").write_text("const a = require('path');\n", encoding="utf-8")

            hyg = check_node_script_hygiene(workspace_root=ws)
            self.assertEqual(hyg["status"], "OK")
            self.assertEqual(hyg["violations"], [])

            py_files, js_files = _discover_workspace_files(ws)
            self.assertEqual(py_files, [])
            self.assertEqual([p.relative_to(ws).as_posix() for p in js_files], ["src/app.js"])

            smells = audit_structural_smells(ws, target_pkg="src")
            self.assertEqual(smells, [])
            rep = audit_architectural_fitness(workspace_root=ws, target_pkg="src")
            self.assertEqual(rep.status, "PASS")


if __name__ == "__main__":
    unittest.main()
