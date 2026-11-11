# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Verification suite for Architectural Fitness & Macro Governance Framework (ADR-014 / Phase 1).

Validates:
- Native, zero-dependency AFF engine in harness.runtime.aff
- Boundary defect auditing (Bifurcation, Layer Direction, Cleanroom Membrane)
- Dependency cycle detection (DFS on AST import graph)
- Structural smell auditing (Foreign language monolith, God component, Unbounded cache)
- Sub-second benchmark invariant (<0.25s)
- CLI integration (agyis audit aff/macro/fitness)
- Doctor integration (check_architectural_fitness in doctor.py)
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from harness.commands.audit import cmd_audit
from harness.runtime.aff import (
    BoundaryDefect,
    BoundaryRule,
    CycleDefect,
    DEFAULT_BOUNDARY_RULES,
    SmellDefect,
    aff_exempt,
    audit_architectural_fitness,
    audit_dependency_cycles,
    audit_import_boundaries,
    audit_structural_smells,
)
from harness.runtime.doctor import check_architectural_fitness, run_doctor


class TestArchitecturalFitnessEngine(unittest.TestCase):
    """Test suite validating core AFF data models, defect detection, and scoring."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_clean_modular_project_passes_with_perfect_score(self) -> None:
        """A clean modular project with proper layering yields status PASS and score 100.0."""
        pkg = self.workspace / "app"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "models.py").write_text("class User:\n    pass\n", encoding="utf-8")
        (pkg / "service.py").write_text(
            "from app.models import User\n\ndef get_user() -> User:\n    return User()\n",
            encoding="utf-8",
        )

        report = audit_architectural_fitness(workspace_root=self.workspace, target_pkg="app")
        self.assertEqual(report.status, "PASS")
        self.assertEqual(report.score, 100.0)
        self.assertEqual(len(report.boundary_defects), 0)
        self.assertEqual(len(report.cycle_defects), 0)
        self.assertEqual(len(report.smell_defects), 0)
        self.assertGreater(report.scanned_files_count, 0)
        self.assertLess(report.benchmark_latency_s, 0.25)

    def test_boundary_defect_caught_with_exact_metadata(self) -> None:
        """Illegal import across defined boundary rule raises BoundaryDefect with line and rule."""
        core_dir = self.workspace / "core"
        infra_dir = self.workspace / "infra"
        core_dir.mkdir(parents=True, exist_ok=True)
        infra_dir.mkdir(parents=True, exist_ok=True)

        (core_dir / "__init__.py").write_text("", encoding="utf-8")
        (infra_dir / "__init__.py").write_text("", encoding="utf-8")
        (infra_dir / "db.py").write_text("class Database:\n    pass\n", encoding="utf-8")

        core_service = core_dir / "service.py"
        core_service.write_text(
            "import infra.db\n\ndef query():\n    return infra.db.Database()\n",
            encoding="utf-8",
        )

        custom_rules = [
            BoundaryRule(
                source_pattern="core/**",
                forbidden_targets=["infra"],
                rule_name="NO_INFRA_IN_CORE",
                severity="CRITICAL",
                description="Core domain must not depend directly on infrastructure layer.",
                remediation="Invert dependency using dependency injection or interfaces.",
            )
        ]

        defects = audit_import_boundaries(root_dir=self.workspace, rules=custom_rules)
        self.assertEqual(len(defects), 1)
        d = defects[0]
        self.assertEqual(d.source_file, "core/service.py")
        self.assertEqual(d.line_number, 1)
        self.assertEqual(d.imported_module, "infra.db")
        self.assertEqual(d.rule_name, "NO_INFRA_IN_CORE")
        self.assertEqual(d.severity, "CRITICAL")
        self.assertIn("Invert dependency", d.remediation)

    def test_bifurcation_invariant_default_rule(self) -> None:
        """Distributable harness importing pipeline triggers BIFURCATION_INVARIANT defect."""
        harness_dir = self.workspace / "harness"
        harness_dir.mkdir(parents=True, exist_ok=True)
        (harness_dir / "__init__.py").write_text("", encoding="utf-8")

        bad_module = harness_dir / "bad_mod.py"
        bad_module.write_text(
            "from pipeline import extract_transcripts\n",
            encoding="utf-8",
        )

        defects = audit_import_boundaries(root_dir=self.workspace)
        bifurcation_defects = [d for d in defects if d.rule_name == "BIFURCATION_INVARIANT"]
        self.assertEqual(len(bifurcation_defects), 1)
        self.assertEqual(bifurcation_defects[0].source_file, "harness/bad_mod.py")
        self.assertEqual(bifurcation_defects[0].line_number, 1)

    def test_layer_direction_default_rule(self) -> None:
        """Harness runtime importing commands triggers LAYER_DIRECTION defect."""
        runtime_dir = self.workspace / "harness" / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        (self.workspace / "harness" / "__init__.py").write_text("", encoding="utf-8")
        (runtime_dir / "__init__.py").write_text("", encoding="utf-8")

        runtime_file = runtime_dir / "leaky_worker.py"
        runtime_file.write_text(
            "from harness.commands.doctor import cmd_doctor\n",
            encoding="utf-8",
        )

        defects = audit_import_boundaries(root_dir=self.workspace)
        layer_defects = [d for d in defects if d.rule_name == "LAYER_DIRECTION"]
        self.assertEqual(len(layer_defects), 1)
        self.assertEqual(layer_defects[0].source_file, "harness/runtime/leaky_worker.py")
        self.assertEqual(layer_defects[0].line_number, 1)

    def test_cleanroom_membrane_default_rule(self) -> None:
        """Harness importing dirtyroom triggers CLEANROOM_MEMBRANE defect."""
        harness_dir = self.workspace / "harness"
        harness_dir.mkdir(parents=True, exist_ok=True)
        (harness_dir / "__init__.py").write_text("", encoding="utf-8")

        cleanroom_violation = harness_dir / "tainted.py"
        cleanroom_violation.write_text(
            "import dirtyroom.ghidra\n",
            encoding="utf-8",
        )

        defects = audit_import_boundaries(root_dir=self.workspace)
        cleanroom_defects = [d for d in defects if d.rule_name == "CLEANROOM_MEMBRANE"]
        self.assertEqual(len(cleanroom_defects), 1)
        self.assertEqual(cleanroom_defects[0].source_file, "harness/tainted.py")

    def test_boundary_exemption_honored(self) -> None:
        """Exempted paths and line pragmas are not flagged as boundary defects."""
        harness_dir = self.workspace / "harness"
        harness_dir.mkdir(parents=True, exist_ok=True)
        (harness_dir / "__init__.py").write_text("", encoding="utf-8")

        # 1. Rule level exemption
        audit_file = harness_dir / "commands" / "audit.py"
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        audit_file.write_text("from pipeline import extract\n", encoding="utf-8")

        # 2. Line pragma exemption
        pragma_file = harness_dir / "pragmatic.py"
        pragma_file.write_text(
            "from pipeline import extract  # aff: exempt\n",
            encoding="utf-8",
        )

        defects = audit_import_boundaries(root_dir=self.workspace)
        self.assertEqual(len(defects), 0)

    def test_circular_import_detection_two_nodes(self) -> None:
        """Circular dependency A -> B -> A is detected with exact cycle path."""
        pkg = self.workspace / "pkg"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")

        (pkg / "a.py").write_text("import pkg.b\n", encoding="utf-8")
        (pkg / "b.py").write_text("import pkg.a\n", encoding="utf-8")

        cycles = audit_dependency_cycles(root_dir=self.workspace, target_pkg="pkg")
        self.assertEqual(len(cycles), 1)
        path = cycles[0].cycle_path
        self.assertIn("pkg.a", path)
        self.assertIn("pkg.b", path)
        self.assertEqual(path[0], path[-1])

    def test_circular_import_detection_three_nodes(self) -> None:
        """Circular dependency A -> B -> C -> A is detected with full 3-node cycle path."""
        pkg = self.workspace / "triangle"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")

        (pkg / "a.py").write_text("from triangle.b import b_func\n", encoding="utf-8")
        (pkg / "b.py").write_text("from triangle.c import c_func\n", encoding="utf-8")
        (pkg / "c.py").write_text("from triangle.a import a_func\n", encoding="utf-8")

        cycles = audit_dependency_cycles(root_dir=self.workspace, target_pkg="triangle")
        self.assertEqual(len(cycles), 1)
        self.assertEqual(len(cycles[0].cycle_path), 4)
        self.assertEqual(cycles[0].cycle_path[0], cycles[0].cycle_path[-1])

    def test_foreign_language_monolith_smell_detected(self) -> None:
        """Multiline string constant (>100 lines) with HTML/JS/CSS triggers FOREIGN_LANGUAGE_MONOLITH."""
        pkg = self.workspace / "web"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")

        # Generate 120 lines of JS inside a Python multiline string
        js_lines = ['script = """']
        js_lines.append("<!DOCTYPE html><html><head><script>")
        for i in range(110):
            js_lines.append(f"  function handler_{i}() {{ document.getElementById('btn').addEventListener('click', () => {{}}); }}")
        js_lines.append("</script></head><body><div>Content</div></body></html>")
        js_lines.append('"""')

        (pkg / "monolith.py").write_text("\n".join(js_lines) + "\n", encoding="utf-8")

        smells = audit_structural_smells(root_dir=self.workspace, target_pkg="web")
        foreign_smells = [s for s in smells if s.smell_type == "FOREIGN_LANGUAGE_MONOLITH"]
        self.assertEqual(len(foreign_smells), 1)
        self.assertEqual(foreign_smells[0].file, "web/monolith.py")
        self.assertEqual(foreign_smells[0].severity, "MAJOR")
        self.assertIn("assets/", foreign_smells[0].remediation)

    def test_god_component_definitions_smell_and_aff_exempt(self) -> None:
        """Module with >30 top-level definitions triggers GOD_COMPONENT unless @aff_exempt."""
        pkg = self.workspace / "god"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")

        def_lines = []
        for i in range(35):
            def_lines.append(f"def operation_{i}():\n    return {i}\n")
        (pkg / "monolith.py").write_text("\n".join(def_lines), encoding="utf-8")

        smells = audit_structural_smells(root_dir=self.workspace, target_pkg="god")
        god_smells = [s for s in smells if s.smell_type == "GOD_COMPONENT"]
        self.assertEqual(len(god_smells), 1)
        self.assertIn("35 top-level definitions", god_smells[0].description)

        # Now exempt 10 definitions with @aff_exempt so remaining count is 25 (<=30)
        exempt_lines = ["from harness.runtime.aff import aff_exempt\n"]
        for i in range(10):
            exempt_lines.append(f"@aff_exempt\ndef operation_{i}():\n    return {i}\n")
        for i in range(10, 35):
            exempt_lines.append(f"def operation_{i}():\n    return {i}\n")
        (pkg / "monolith.py").write_text("\n".join(exempt_lines), encoding="utf-8")

        smells_after = audit_structural_smells(root_dir=self.workspace, target_pkg="god")
        god_smells_after = [s for s in smells_after if s.smell_type == "GOD_COMPONENT"]
        self.assertEqual(len(god_smells_after), 0)

    def test_unbounded_cache_smell_detected(self) -> None:
        """Assignment to cache dictionary inside method without capacity guard triggers UNBOUNDED_CACHE."""
        pkg = self.workspace / "cache_pkg"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")

        (pkg / "leaky.py").write_text(
            "class Worker:\n"
            "    def __init__(self):\n"
            "        self.cache = {}\n"
            "    def execute(self, key, val):\n"
            "        self.cache[key] = val\n",
            encoding="utf-8",
        )

        smells = audit_structural_smells(root_dir=self.workspace, target_pkg="cache_pkg")
        cache_smells = [s for s in smells if s.smell_type == "UNBOUNDED_CACHE"]
        self.assertEqual(len(cache_smells), 1)
        self.assertEqual(cache_smells[0].file, "cache_pkg/leaky.py")
        self.assertEqual(cache_smells[0].severity, "MAJOR")

        # Bounded cache with len() guard does NOT trigger smell
        (pkg / "bounded.py").write_text(
            "class BoundedWorker:\n"
            "    def __init__(self):\n"
            "        self.cache = {}\n"
            "        self.limit = 100\n"
            "    def execute(self, key, val):\n"
            "        if len(self.cache) >= self.limit:\n"
            "            self.cache.pop(next(iter(self.cache)))\n"
            "        self.cache[key] = val\n",
            encoding="utf-8",
        )

        smells_bounded = audit_structural_smells(root_dir=self.workspace, target_pkg="cache_pkg")
        bounded_smells = [s for s in smells_bounded if s.file == "cache_pkg/bounded.py"]
        self.assertEqual(len(bounded_smells), 0)

    def test_aff_benchmark_latency_sub_quarter_second(self) -> None:
        """The AFF engine benchmark latency strictly satisfies ADR-015 (<0.25 seconds)."""
        pkg = self.workspace / "bench_pkg"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        for i in range(10):
            (pkg / f"mod_{i}.py").write_text(
                f"def compute_{i}():\n    return {i} * 2\n",
                encoding="utf-8",
            )

        start = time.perf_counter()
        report = audit_architectural_fitness(workspace_root=self.workspace, target_pkg="bench_pkg")
        elapsed = time.perf_counter() - start

        self.assertLess(report.benchmark_latency_s, 0.25)
        self.assertLess(elapsed, 0.25)
        self.assertEqual(report.status, "PASS")
        self.assertEqual(report.score, 100.0)


class TestCliAndDoctorAffIntegration(unittest.TestCase):
    """Test suite validating CLI registration and Doctor structural fitness integration."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

        # Scaffolding clean project
        app_dir = self.workspace / "harness"
        app_dir.mkdir(parents=True, exist_ok=True)
        (app_dir / "__init__.py").write_text("", encoding="utf-8")
        (app_dir / "worker.py").write_text("def run():\n    return 42\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_cmd_audit_aff_json_mode(self) -> None:
        """cmd_audit with stage 'aff' and --json outputs valid JSON report."""
        args = argparse.Namespace(
            stage="aff",
            workspace=self.workspace,
            json=True,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_audit(args)
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertEqual(data["status"], "PASS")
            self.assertEqual(data["score"], 100.0)
            self.assertIn("scanned_files_count", data)

    def test_cmd_audit_macro_and_fitness_aliases(self) -> None:
        """cmd_audit recognizes 'macro' and 'fitness' aliases."""
        for alias in ("macro", "fitness"):
            args = argparse.Namespace(
                stage=alias,
                workspace=self.workspace,
                json=True,
            )
            with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                code = cmd_audit(args)
                self.assertEqual(code, 0)
                data = json.loads(mock_out.getvalue().strip())
                self.assertEqual(data["status"], "PASS")

    def test_cmd_audit_aff_human_mode(self) -> None:
        """cmd_audit with stage 'aff' outputs formatted terminal report with colored badges."""
        args = argparse.Namespace(
            stage="aff",
            workspace=self.workspace,
            json=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_audit(args)
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertIn("Agyis Architectural Fitness Function", out)
            self.assertIn("Status:          PASS", out)
            self.assertIn("Fitness Score:   100.0/100", out)

    def test_check_architectural_fitness_helper(self) -> None:
        """check_architectural_fitness helper correctly identifies clean harness structure."""
        res = check_architectural_fitness(self.workspace)
        self.assertIsNotNone(res)
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["score"], 100.0)

        # None workspace returns None
        self.assertIsNone(check_architectural_fitness(None))

    def test_run_doctor_includes_architectural_fitness_section(self) -> None:
        """run_doctor executed on workspace with harness/ includes architectural_fitness dictionary."""
        audit = run_doctor(workspace_root=self.workspace)
        self.assertIn("architectural_fitness", audit)
        self.assertIsNotNone(audit["architectural_fitness"])
        self.assertEqual(audit["architectural_fitness"]["status"], "PASS")

    def test_syntax_error_in_corrupted_file_recorded_as_critical_smell(self) -> None:
        """Unparseable or corrupted Python file produces CRITICAL SYNTAX_ERROR SmellDefect (DEFECT-01)."""
        pkg = self.workspace / "corrupted"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")

        report = audit_architectural_fitness(workspace_root=self.workspace, target_pkg="corrupted")
        self.assertEqual(report.status, "FAIL")
        syntax_smells = [s for s in report.smell_defects if s.smell_type == "SYNTAX_ERROR"]
        self.assertEqual(len(syntax_smells), 1)
        self.assertEqual(syntax_smells[0].severity, "CRITICAL")
        self.assertEqual(syntax_smells[0].file, "corrupted/broken.py")

    def test_doctor_runtime_check_captures_exceptions_as_fail(self) -> None:
        """Doctor check_architectural_fitness returns structured FAIL dict on unexpected exception (DEFECT-02)."""
        with patch("harness.runtime.aff.audit_architectural_fitness", side_effect=RuntimeError("Disk failure")):
            res = check_architectural_fitness(self.workspace)
            self.assertIsNotNone(res)
            self.assertEqual(res["status"], "FAIL")
            self.assertEqual(res["score"], 0.0)
            self.assertIn("Disk failure", res["error"])
            self.assertIn("AFF evaluation crashed", res["details"])

    def test_matches_forbidden_target_no_false_positives_on_substrings(self) -> None:
        """_matches_forbidden_target matches exact or dot-separated prefix without substring false positives (DEFECT-03)."""
        from harness.runtime.aff import _matches_forbidden_target

        self.assertFalse(_matches_forbidden_target("my_package.dirtyroom_mock", ".dirtyroom"))
        self.assertFalse(_matches_forbidden_target("pipeline_extra", "pipeline"))
        self.assertTrue(_matches_forbidden_target("dirtyroom", ".dirtyroom"))
        self.assertTrue(_matches_forbidden_target("dirtyroom.sub", ".dirtyroom"))
        self.assertTrue(_matches_forbidden_target("pipeline", "pipeline"))
        self.assertTrue(_matches_forbidden_target("pipeline.extract", "pipeline"))

    def test_unbounded_cache_detects_unrelated_len_call_as_unbounded(self) -> None:
        """len() called on unrelated parameter does not suppress UNBOUNDED_CACHE defect (DEFECT-04)."""
        pkg = self.workspace / "cache_unrelated"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "handler.py").write_text(
            "class UnrelatedWorker:\n"
            "    def __init__(self):\n"
            "        self.cache = {}\n"
            "    def process(self, items, key, val):\n"
            "        count = len(items)\n"  # unrelated len call!
            "        self.cache[key] = val\n",
            encoding="utf-8",
        )

        smells = audit_structural_smells(root_dir=self.workspace, target_pkg="cache_unrelated")
        cache_smells = [s for s in smells if s.smell_type == "UNBOUNDED_CACHE"]
        self.assertEqual(len(cache_smells), 1)
        self.assertEqual(cache_smells[0].file, "cache_unrelated/handler.py")

    def test_god_component_line_limit_and_js_asset_enforcement(self) -> None:
        """Python modules and JS assets exceeding 800 lines or >25 defs trigger GOD_COMPONENT."""
        pkg = self.workspace / "tight_pkg"
        assets = pkg / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")

        # 26 top-level defs triggers (>25 threshold)
        (pkg / "many_defs.py").write_text(
            "\n".join(f"def fn_{i}():\n    return {i}" for i in range(26)) + "\n",
            encoding="utf-8",
        )
        # 805 lines triggers (>800 line limit)
        (pkg / "long_py.py").write_text("\n".join(f"X_{i} = {i}" for i in range(805)) + "\n", encoding="utf-8")
        # 805-line JS asset triggers (>800 line limit)
        (assets / "big_hud.js").write_text("\n".join(f"const v{i} = {i};" for i in range(805)) + "\n", encoding="utf-8")

        smells = audit_structural_smells(root_dir=self.workspace, target_pkg="tight_pkg")
        god_files = {s.file for s in smells if s.smell_type == "GOD_COMPONENT"}
        self.assertIn("tight_pkg/many_defs.py", god_files)
        self.assertIn("tight_pkg/long_py.py", god_files)
        self.assertIn("tight_pkg/assets/big_hud.js", god_files)


if __name__ == "__main__":
    unittest.main()

