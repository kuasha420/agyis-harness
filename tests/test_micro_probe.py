#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Comprehensive Unit and Contract Test Suite for Diff-Aware In-Harness Micro-Mutator Engine.

Governing Specifications:
- ORIGINAL_REQUEST.md (§R2 Diff-Aware In-Harness Micro-Mutator Engine)
- PROJECT.md (§M2 Interface Contracts)
- TEST_READY.md (Milestone M2 Verification)

Architectural Invariants Enforced:
1. Hermetic Isolation: Tests execute in temporary clean-room workspaces.
2. Sub-Second Benchmark Invariant: Entire suite executes in <0.5s.
3. Zero-Facade Integrity: Explicit, derived test assertions against real logic.
"""

from __future__ import annotations

import ast
import io
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any, Dict, List
import unittest
from unittest.mock import MagicMock, patch

from harness.cli import build_parser, main as cli_main
from harness.mutation.micro_probe import (
    ACTIVE_BACKUPS,
    FunctionMutant,
    MutationCandidate,
    MutationConfig,
    MutationResult,
    SurvivingMutant,
    _restore_all_backups,
    apply_operator,
    extract_diff_mutation_candidates,
    generate_function_mutants,
    has_no_mutant_pragma,
    is_arid_line,
    mutate_python_source,
    mutate_token_source,
    run_micro_mutation,
)


class TestMicroProbeUnit(unittest.TestCase):
    """Hermetic unit tests for all micro-probe operators, parsers, and transformers."""

    # -----------------------------------------------------------------------
    # Operator 1: Condition Inversion
    # -----------------------------------------------------------------------
    def test_condition_inversion_eq_to_noteq(self) -> None:
        src = "if status == 'READY': pass"
        mutated = apply_operator(src, "condition_inversion")
        self.assertIn("status != 'READY'", mutated)

    def test_condition_inversion_noteq_to_eq(self) -> None:
        src = "if code != 0: return False"
        mutated = apply_operator(src, "condition_inversion")
        self.assertIn("code == 0", mutated)

    def test_condition_inversion_lt_to_gte(self) -> None:
        src = "if count < 10: pass"
        mutated = apply_operator(src, "condition_inversion")
        self.assertIn("count >= 10", mutated)

    def test_condition_inversion_gt_to_lte(self) -> None:
        src = "if val > 0: pass"
        mutated = apply_operator(src, "condition_inversion")
        self.assertIn("val <= 0", mutated)

    def test_condition_inversion_is_to_is_not(self) -> None:
        src = "if obj is None: return"
        mutated = apply_operator(src, "condition_inversion")
        self.assertIn("obj is not None", mutated)

    def test_condition_inversion_in_to_not_in(self) -> None:
        src = "if item in collection: pass"
        mutated = apply_operator(src, "condition_inversion")
        self.assertIn("item not in collection", mutated)

    # -----------------------------------------------------------------------
    # Operator 2: Logical Operator Swap
    # -----------------------------------------------------------------------
    def test_logical_swap_and_to_or(self) -> None:
        src = "if is_valid and has_quota: pass"
        mutated = apply_operator(src, "logical_swap")
        self.assertIn("is_valid or has_quota", mutated)

    def test_logical_swap_or_to_and(self) -> None:
        src = "while retry or active: pass"
        mutated = apply_operator(src, "logical_swap")
        self.assertIn("retry and active", mutated)

    # -----------------------------------------------------------------------
    # Operator 3: Boundary Shift
    # -----------------------------------------------------------------------
    def test_boundary_shift_add_one_to_sub_one(self) -> None:
        src = "return offset + 1"
        mutated = apply_operator(src, "boundary_shift")
        self.assertIn("offset - 1", mutated)

    def test_boundary_shift_sub_one_to_add_one(self) -> None:
        src = "return offset - 1"
        mutated = apply_operator(src, "boundary_shift")
        self.assertIn("offset + 1", mutated)

    def test_boundary_shift_relational_gt_to_gte(self) -> None:
        src = "if count > 0: pass"
        mutated = apply_operator(src, "boundary_shift")
        self.assertIn("count >= 0", mutated)

    def test_boundary_shift_relational_lt_to_lte(self) -> None:
        src = "if idx < max_len: pass"
        mutated = apply_operator(src, "boundary_shift")
        self.assertIn("idx <= max_len", mutated)

    # -----------------------------------------------------------------------
    # Operator 4: Return Value Stubbing
    # -----------------------------------------------------------------------
    def test_return_stub_object_to_none(self) -> None:
        src = "return user_record"
        mutated = apply_operator(src, "return_stub")
        self.assertIn("return None", mutated)

    def test_return_stub_bool_true_to_false(self) -> None:
        src = "return True"
        mutated = apply_operator(src, "return_stub")
        self.assertIn("return False", mutated)

    def test_return_stub_bool_false_to_true(self) -> None:
        src = "return False"
        mutated = apply_operator(src, "return_stub")
        self.assertIn("return True", mutated)

    def test_return_stub_bare_return_to_false(self) -> None:
        src = "return"
        mutated = apply_operator(src, "return_stub")
        self.assertIn("return False", mutated)

    # -----------------------------------------------------------------------
    # Operator 5: Void Statement Deletion
    # -----------------------------------------------------------------------
    def test_void_statement_deletion_call_to_pass(self) -> None:
        src = "cache.set('key', value)"
        mutated = apply_operator(src, "void_statement_delete")
        self.assertEqual(mutated.strip(), "pass")

    # -----------------------------------------------------------------------
    # Operator 6: Literal Inversion
    # -----------------------------------------------------------------------
    def test_literal_mutation_true_to_false(self) -> None:
        src = "enabled = True"
        mutated = apply_operator(src, "literal_mutation")
        self.assertIn("enabled = False", mutated)

    def test_literal_mutation_false_to_true(self) -> None:
        src = "is_active = False"
        mutated = apply_operator(src, "literal_mutation")
        self.assertIn("is_active = True", mutated)

    # -----------------------------------------------------------------------
    # Arid-Line Suppression
    # -----------------------------------------------------------------------
    def test_arid_line_suppression_comprehensive(self) -> None:
        arid_samples = [
            "import os",
            "from pathlib import Path",
            "import { Header } from './Header';",
            "use std::collections::HashMap;",
            "const fs = require('fs');",
            "# This is a Python comment",
            "// This is a TS comment",
            "/* Block comment */",
            "* inside comment",
            '"""Module docstring"""',
            "'''Single quoted docstring'''",
            "type UserID = string | number;",
            "interface Config { debug: boolean }",
            "typedef unsigned long ulong;",
            "print('Debug trace')",
            "console.log('User logged in')",
            "console.error('Failed request')",
            "logger.info('Task completed')",
            "logger.debug('Memory allocation')",
            "logging.warning('Disk high')",
            "   \t  \n",
        ]
        for line in arid_samples:
            self.assertTrue(is_arid_line(line), f"Expected '{line}' to be identified as arid")

    def test_non_arid_logic_lines_not_suppressed(self) -> None:
        logic_samples = [
            "if x == 0:",
            "return True",
            "x = compute(a, b)",
            "for item in items:",
            "while active:",
            "offset = index + 1",
            "cache.invalidate(key)",
        ]
        for line in logic_samples:
            self.assertFalse(is_arid_line(line), f"Expected '{line}' to NOT be arid")

    # -----------------------------------------------------------------------
    # Inline Pragma Suppression
    # -----------------------------------------------------------------------
    def test_has_no_mutant_pragma_syntax_variations(self) -> None:
        valid_pragmas = [
            "if x >= 0:  # agyis: no-mutant boundary clamped upstream",
            "return count + 1  # agyis:no-mutant equivalent branch",
            "x = y  // agyis: no-mutant TS equivalent",
            "return 0  # AGYIS: NO-MUTANT upper case",
            "return 1  #   agyis:   no-mutant   spaced",
            "return 2\t#agyis:no-mutant\t",
            "return 3  # agyis: no-mutant Unicode description (α -> β)",
        ]
        for p in valid_pragmas:
            self.assertTrue(has_no_mutant_pragma(p), f"Pragma not detected: '{p}'")

    def test_has_no_mutant_pragma_negative(self) -> None:
        non_pragmas = [
            "if x == 0:  # normal comment",
            "return False",
            "# agyis: other-command",
            "// TODO: agyis fix later",
        ]
        for np in non_pragmas:
            self.assertFalse(has_no_mutant_pragma(np), f"False positive pragma on: '{np}'")

    # -----------------------------------------------------------------------
    # AST Coordinate Splicing & Formatting Preservation
    # -----------------------------------------------------------------------
    def test_ast_surgical_splicing_preserves_comments_and_whitespace(self) -> None:
        src = (
            "# Top-level module banner\n"
            "class Engine:\n"
            "    # inner comment\n"
            "    def check(self, val: int) -> bool:\n"
            "        # check non-zero\n"
            "        if val == 0:\n"
            "            return False\n"
            "        return True\n"
        )
        mutated, diff = mutate_python_source(src, target_line=6, operator="condition_inversion")
        self.assertIn("# Top-level module banner", mutated)
        self.assertIn("# inner comment", mutated)
        self.assertIn("# check non-zero", mutated)
        self.assertIn("if val != 0:", mutated)
        self.assertIn("-        if val == 0:", diff)
        self.assertIn("+        if val != 0:", diff)

    # -----------------------------------------------------------------------
    # Function Mutant Diversity Sampling
    # -----------------------------------------------------------------------
    def test_function_diversity_sampling_capped_at_five_to_six(self) -> None:
        func_code = (
            "def evaluate(a, b, c, d):\n"
            "    if a == 1 and b == 2 and c == 3:\n"
            "        x = a + 1\n"
            "        y = b + 2\n"
            "        do_something(x)\n"
            "        return True\n"
            "    return False\n"
        )
        mutants = generate_function_mutants(func_code, max_mutants=6)
        self.assertLessEqual(len(mutants), 6)
        self.assertGreaterEqual(len(mutants), 3)

        ops = {m.operator for m in mutants}
        self.assertGreaterEqual(len(ops), 3, "Mutants must span diverse operators")

    # -----------------------------------------------------------------------
    # Polyglot Token Replacements (TS/JS & Rust)
    # -----------------------------------------------------------------------
    def test_polyglot_ts_strict_equality(self) -> None:
        code = "if (mode === 'STRICT') { return true; }"
        mutated, op = mutate_token_source(code, lang="ts")
        self.assertIn("mode !== 'STRICT'", mutated)
        self.assertEqual(op, "condition_inversion")

    def test_polyglot_rust_logical_and(self) -> None:
        code = "if is_admin && is_active { Ok(()) } else { Err(()) }"
        mutated, op = mutate_token_source(code, lang="rust")
        self.assertIn("is_admin || is_active", mutated)
        self.assertEqual(op, "logical_swap")

    # -----------------------------------------------------------------------
    # Surviving Mutant Actionable Report
    # -----------------------------------------------------------------------
    def test_surviving_mutant_actionable_report_format(self) -> None:
        sm = SurvivingMutant(
            file_path="src/auth.py",
            function_name="verify_token",
            line_number=55,
            operator="condition_inversion",
            diff_snippet="- if tok is not None:\n+ if tok is None:",
            test_target="tests/test_auth.py",
        )
        report = sm.to_actionable_report()
        self.assertIn("src/auth.py:55", report)
        self.assertIn("verify_token", report)
        self.assertIn("condition_inversion", report)
        self.assertIn("- if tok is not None:", report)
        self.assertIn("+ if tok is None:", report)
        self.assertIn("# agyis: no-mutant", report)

    # -----------------------------------------------------------------------
    # Diff Hunk Candidate Parsing
    # -----------------------------------------------------------------------
    def test_diff_candidate_extraction_skips_arid_and_test_files(self) -> None:
        diff_text = (
            "--- a/src/service.py\n"
            "+++ b/src/service.py\n"
            "@@ -20,1 +20,3 @@\n"
            "+import logging\n"
            "+    if count > 5:\n"
            "+        return count\n"
            "--- a/tests/test_service.py\n"
            "+++ b/tests/test_service.py\n"
            "@@ -10,1 +10,1 @@\n"
            "+    self.assertTrue(True)\n"
            "--- a/README.md\n"
            "+++ b/README.md\n"
            "@@ -1,1 +1,1 @@\n"
            "+# Documentation\n"
        )
        candidates = extract_diff_mutation_candidates(diff_text)
        # Should only contain line 21 and 22 from src/service.py (import and non-code skipped)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].file_path, "src/service.py")
        self.assertEqual(candidates[0].line_number, 21)
        self.assertEqual(candidates[1].line_number, 22)

    # -----------------------------------------------------------------------
    # In-Memory Backup & Crash Safety Restoration
    # -----------------------------------------------------------------------
    def test_atomic_backup_restoration_on_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "logic.py"
            original = "def foo():\n    return 42\n"
            p.write_text(original, encoding="utf-8")

            ACTIVE_BACKUPS[p] = original
            p.write_text("def foo():\n    return None\n", encoding="utf-8")

            # Simulate recovery
            _restore_all_backups()
            restored = p.read_text(encoding="utf-8")
            self.assertEqual(restored, original)
            self.assertEqual(len(ACTIVE_BACKUPS), 0)

    # -----------------------------------------------------------------------
    # Clean Diff Fast Path (<50ms)
    # -----------------------------------------------------------------------
    def test_empty_diff_returns_zero_mutants_fast(self) -> None:
        t0 = time.perf_counter()
        res = run_micro_mutation(target_diff="")
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertEqual(res.total_mutants, 0)
        self.assertEqual(res.killed_mutants, 0)
        self.assertEqual(res.exit_code, 0)
        self.assertLess(elapsed_ms, 50.0)

    # -----------------------------------------------------------------------
    # Remediation Suite (Iteration 2 Empirical Invariants)
    # -----------------------------------------------------------------------
    def test_subprocess_timeout_expired_counted_as_killed(self) -> None:
        """Asserts that subprocess.TimeoutExpired is caught and counted as a killed mutant."""
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            src_file = repo / "loop.py"
            orig_code = "def run():\n    if count > 0:\n        return True\n    return False\n"
            src_file.write_text(orig_code, encoding="utf-8")

            diff = (
                "--- a/loop.py\n"
                "+++ b/loop.py\n"
                "@@ -1,4 +1,4 @@\n"
                " def run():\n"
                "+    if count > 0:\n"
                "         return True\n"
                "     return False\n"
            )

            cfg = MutationConfig(repo_root=repo, timeout_sec=0.1)

            with patch("harness.mutation.micro_probe.resolve_affected_tests") as mock_resolve:
                mock_res = MagicMock()
                mock_res.is_empty = False
                mock_res.runner_cmd = "python3 -m unittest"
                mock_resolve.return_value = mock_res

                with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=0.1)):
                    res = run_micro_mutation(target_diff=diff, config=cfg)
                    self.assertGreater(res.killed_mutants, 0)
                    self.assertEqual(len(res.survived_mutants), 0)
                    self.assertEqual(res.exit_code, 0)

            # Assert file restored
            self.assertEqual(src_file.read_text(encoding="utf-8"), orig_code)

    def test_multiline_return_coordinate_splicing(self) -> None:
        """Asserts multiline return tuples/dicts splice cleanly without IndentationError or SyntaxError."""
        code_ml = "def get_payload():\n    return (\n        'alpha',\n        'beta',\n    )\n"
        mut, diff = mutate_python_source(code_ml, target_line=2, operator="return_stub")
        self.assertNotEqual(mut, code_ml)
        self.assertIn("    return None\n", mut)
        ast.parse(mut)

    def test_multiline_call_void_deletion(self) -> None:
        """Asserts multiline calls are replaced with pass without syntax errors."""
        code_call = "def run():\n    service.execute(\n        timeout=10,\n        retry=True,\n    )\n    return True\n"
        mut, diff = mutate_python_source(code_call, target_line=2, operator="void_statement_delete")
        self.assertNotEqual(mut, code_call)
        self.assertIn("    pass\n", mut)
        ast.parse(mut)

    def test_utf8_byte_offset_slicing_multibyte_characters(self) -> None:
        """Asserts Python AST byte-offset slicing correctly handles multibyte UTF-8 characters."""
        code_utf8 = "def notify():\n    # 🚀 Rocket status indicator with multibyte chars\n    return True\n"
        mut, diff = mutate_python_source(code_utf8, target_line=3, operator="return_stub")
        self.assertNotEqual(mut, code_utf8)
        self.assertIn("    return False\n", mut)
        ast.parse(mut)

        # Inline multibyte string
        code_inline = "def emoji():\n    tag = '🔥'; return True\n"
        mut2, diff2 = mutate_python_source(code_inline, target_line=2, operator="return_stub")
        self.assertNotEqual(mut2, code_inline)
        self.assertIn("return False", mut2)
        ast.parse(mut2)

    def test_polyglot_relational_comparisons_less_and_greater(self) -> None:
        """Asserts < and > relational operators are mutated in TS/JS and Rust."""
        mut_ts_lt, op_ts_lt = mutate_token_source("return a < b;", lang="ts")
        self.assertEqual(op_ts_lt, "condition_inversion")
        self.assertEqual(mut_ts_lt, "return a >= b;")

        mut_ts_gt, op_ts_gt = mutate_token_source("return a > b;", lang="ts")
        self.assertEqual(op_ts_gt, "condition_inversion")
        self.assertEqual(mut_ts_gt, "return a <= b;")

        mut_rs_lt, op_rs_lt = mutate_token_source("if a < b {", lang="rs")
        self.assertEqual(op_rs_lt, "condition_inversion")
        self.assertEqual(mut_rs_lt, "if a >= b {")

        mut_rs_gt, op_rs_gt = mutate_token_source("if a > b {", lang="rs")
        self.assertEqual(op_rs_gt, "condition_inversion")
        self.assertEqual(mut_rs_gt, "if a <= b {")

    def test_polyglot_boolean_word_boundaries_and_control_flow_guards(self) -> None:
        """Asserts word boundaries prevent false positives and control keywords are not commented out."""
        # Word boundary: identifier containing 'false' must not mutate
        mut_id, op_id = mutate_token_source("const parse_falsehood = () => {};", lang="ts")
        self.assertEqual(op_id, "")
        self.assertEqual(mut_id, "const parse_falsehood = () => {};")

        # Word boundary: boolean literal false must mutate
        mut_bool, op_bool = mutate_token_source("const flag = false;", lang="ts")
        self.assertEqual(op_bool, "literal_mutation")
        self.assertEqual(mut_bool, "const flag = true;")

        # Control flow keywords with calls: must not be corrupted
        for ctrl in ["if (isValid()) {", "while (hasItems()) {", "switch (getType()) {"]:
            mut_ctrl, op_ctrl = mutate_token_source(ctrl, lang="ts")
            self.assertNotEqual(op_ctrl, "void_statement_delete")
            self.assertNotIn("/*", mut_ctrl)

        # Assignment RHS must not be void-deleted into invalid syntax
        mut_assign, op_assign = mutate_token_source("const token = generateToken();", lang="ts")
        self.assertNotEqual(op_assign, "void_statement_delete")
        self.assertNotIn("/*", mut_assign)

        # Legitimate void calls
        mut_void, op_void = mutate_token_source("cleanup();", lang="ts")
        self.assertEqual(op_void, "void_statement_delete")
        self.assertEqual(mut_void, "/* cleanup(); */")

    def test_async_await_void_statement_delete(self) -> None:
        """Asserts void_statement_delete correctly matches await calls in async functions."""
        code_async = "async def flush():\n    await socket.drain()\n    return True\n"
        mut, diff = mutate_python_source(code_async, target_line=2, operator="void_statement_delete")
        self.assertNotEqual(mut, code_async)
        self.assertIn("    pass\n", mut)
        ast.parse(mut)

        mutants = generate_function_mutants(code_async)
        self.assertTrue(any(m.operator == "void_statement_delete" for m in mutants))

    def test_unary_not_condition_inversion(self) -> None:
        """Asserts condition_inversion inverts 'not x' into 'x'."""
        code_unary = "def is_ready(flag):\n    if not flag:\n        return False\n    return True\n"
        mut, diff = mutate_python_source(code_unary, target_line=2, operator="condition_inversion")
        self.assertNotEqual(mut, code_unary)
        self.assertIn("    if flag:\n", mut)
        ast.parse(mut)

        mutants = generate_function_mutants(code_unary)
        self.assertTrue(any(m.operator == "condition_inversion" for m in mutants))

    def test_nested_binop_avoids_premature_mutation(self) -> None:
        """Asserts visit_BinOp does not mark mutated on non-Add/Sub operators, allowing inner Add/Sub to mutate."""
        code_binop = "def scale(x):\n    return (x + 1) * 2\n"
        mut, diff = mutate_python_source(code_binop, target_line=2, operator="boundary_shift")
        self.assertNotEqual(mut, code_binop)
        self.assertIn("(x - 1) * 2", mut)
        ast.parse(mut)

    def test_return_none_stubbed_to_false(self) -> None:
        """Asserts 'return None' is stubbed to 'return False'."""
        code_ret = "def get_val():\n    return None\n"
        mut, diff = mutate_python_source(code_ret, target_line=2, operator="return_stub")
        self.assertNotEqual(mut, code_ret)
        self.assertIn("    return False\n", mut)
        ast.parse(mut)

        self.assertEqual(apply_operator("return None", "return_stub"), "return False")

    # -----------------------------------------------------------------------
    # CLI Parser Registration
    # -----------------------------------------------------------------------
    def test_cli_parser_has_mutation_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["test", "--mutation"])
        self.assertTrue(args.mutation)


if __name__ == "__main__":
    unittest.main()
