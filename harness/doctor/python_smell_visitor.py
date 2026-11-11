# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Python AST visitor for anti-synthetic test smell detection (SM001-SM005)."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from harness.doctor.smell_models import (
    ADAPTER_DECORATORS,
    ADAPTER_PATTERNS,
    BOUNDARY_MODULES,
    BOUNDARY_PATH_KEYWORDS,
    BoundaryExemptionRecord,
    JS_BUILTIN_PASCAL_CASE,
    PYTHON_MOCK_ASSERT_ATTRS,
    PYTHON_STATE_ASSERT_ATTRS,
    SmellSeverity,
    SmellType,
    TestSmell,
    VRT_DIFF_INDICATORS,
    _extract_nested_leaf_values,
    _get_context_snippet,
    _is_excluded_echo_scalar,
    _is_literal_constant,
    _is_mock_call_inspection,
    _is_rule_suppressed,
    _is_trivial_call_assertion,
    _is_trivial_expression,
)


class PythonTestSmellVisitor(ast.NodeVisitor):
    """AST Visitor auditing Python test functions for synthetic test smells."""

    def __init__(self, file_path: str, lines: List[str], pragmas: Dict[int, Set[str]]):
        self.file_path = file_path
        self.lines = lines
        self.pragmas = pragmas
        self.smells: List[TestSmell] = []
        self.exemptions: List[BoundaryExemptionRecord] = []
        self.scanned_tests = 0
        # Maps local symbol name -> qualified module name (e.g. "sp" -> "subprocess", "run" -> "subprocess.run")
        self.boundary_symbols: Dict[str, str] = {}
        self.class_boundary_modules: List[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            base_mod = alias.name.split(".")[0]
            if base_mod in BOUNDARY_MODULES or alias.name in BOUNDARY_MODULES:
                local_name = alias.asname or alias.name
                self.boundary_symbols[local_name] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            base_mod = node.module.split(".")[0]
            if base_mod in BOUNDARY_MODULES or node.module in BOUNDARY_MODULES:
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    self.boundary_symbols[local_name] = f"{node.module}.{alias.name}"
                self.boundary_symbols[node.module] = node.module
                self.boundary_symbols[base_mod] = base_mod
        self.generic_visit(node)

    def _collect_patch_boundary_mods(self, call: ast.Call, out: List[str], check_object: bool = True) -> None:
        """Append boundary patch targets referenced via patch(...) or patch.object(...)."""
        for arg in call.args:
            val = self._extract_constant_value(arg)
            if isinstance(val, str):
                for mod in BOUNDARY_MODULES:
                    if val == mod or val.startswith(f"{mod}."):
                        patch_desc = f"patch:{mod}"
                        if patch_desc not in out:
                            out.append(patch_desc)
        if check_object and isinstance(call.func, ast.Attribute) and call.func.attr == "object" and call.args:
            first_arg = call.args[0]
            if isinstance(first_arg, ast.Name) and first_arg.id in self.boundary_symbols:
                patch_desc = f"patch.object:{self.boundary_symbols[first_arg.id]}"
                if patch_desc not in out:
                    out.append(patch_desc)

    def _collect_decorator_boundaries(self, decorators: List[ast.expr], out: List[str], check_object: bool) -> None:
        """Inspect @adapter_boundary / @patch(...) decorators for boundary exemptions."""
        for decorator in decorators:
            if isinstance(decorator, ast.Name) and decorator.id in ADAPTER_DECORATORS:
                out.append(f"dec:{decorator.id}")
            elif isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name) and decorator.func.id in ADAPTER_DECORATORS:
                    out.append(f"dec:{decorator.func.id}")
                self._collect_patch_boundary_mods(decorator, out, check_object=check_object)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Inspects class-level patch decorators and class name for boundary adapters."""
        prev_class_boundary = list(self.class_boundary_modules)
        if ADAPTER_PATTERNS.search(node.name) or any(kw in node.name.lower() for kw in BOUNDARY_PATH_KEYWORDS):
            self.class_boundary_modules.append(f"class:{node.name}")
        self._collect_decorator_boundaries(node.decorator_list, self.class_boundary_modules, check_object=False)
        self.generic_visit(node)
        self.class_boundary_modules = prev_class_boundary

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._audit_test_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._audit_test_function(node)

    def _is_test_function(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> bool:
        return node.name.startswith("test_") or node.name.endswith("_test")

    def _extract_constant_value(self, node: ast.AST) -> Optional[Any]:
        """Safely extracts a literal constant value from an AST node."""
        if isinstance(node, ast.Name):
            if hasattr(self, "_current_local_constants") and node.id in self._current_local_constants:
                return self._current_local_constants[node.id]
            return None
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Dict):
            res = {}
            for k, v in zip(node.keys, node.values):
                if k and isinstance(k, ast.Constant):
                    res[str(k.value)] = self._extract_constant_value(v)
            return res
        elif isinstance(node, (ast.List, ast.Tuple)):
            return [self._extract_constant_value(elt) for elt in node.elts]
        return None

    def _is_mock_call_inspection(self, node: ast.AST) -> bool:
        return _is_mock_call_inspection(node)

    def _is_literal_constant(self, node: ast.AST) -> bool:
        return _is_literal_constant(node)

    def _is_trivial_expression(self, node: ast.AST) -> bool:
        return _is_trivial_expression(node)

    def _is_trivial_call_assertion(self, attr_name: str, args: List[ast.AST]) -> bool:
        return _is_trivial_call_assertion(attr_name, args)

    def _collect_func_boundaries(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> List[str]:
        """Determine boundary adapter modules referenced by decorators, context managers, and imports."""
        func_boundary_modules: List[str] = list(self.class_boundary_modules)
        stem = Path(self.file_path).stem
        if ADAPTER_PATTERNS.search(stem) or any(kw in str(self.file_path).lower() for kw in BOUNDARY_PATH_KEYWORDS):
            func_boundary_modules.append(f"file:{stem}")

        self._collect_decorator_boundaries(node.decorator_list, func_boundary_modules, check_object=True)

        for subnode in ast.walk(node):
            if subnode is node:
                continue
            if isinstance(subnode, ast.With):
                for item in subnode.items:
                    if isinstance(item.context_expr, ast.Call):
                        self._collect_patch_boundary_mods(item.context_expr, func_boundary_modules, check_object=True)
            elif isinstance(subnode, ast.Name) and subnode.id in self.boundary_symbols:
                mod_name = self.boundary_symbols[subnode.id]
                if mod_name not in func_boundary_modules:
                    func_boundary_modules.append(mod_name)
            elif isinstance(subnode, ast.Import):
                for alias in subnode.names:
                    base_mod = alias.name.split(".")[0]
                    if (base_mod in BOUNDARY_MODULES or alias.name in BOUNDARY_MODULES) and alias.name not in func_boundary_modules:
                        func_boundary_modules.append(alias.name)
            elif isinstance(subnode, ast.ImportFrom) and subnode.module:
                base_mod = subnode.module.split(".")[0]
                if (base_mod in BOUNDARY_MODULES or subnode.module in BOUNDARY_MODULES) and subnode.module not in func_boundary_modules:
                    func_boundary_modules.append(subnode.module)
        return func_boundary_modules

    def _audit_test_function(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> None:
        if not self._is_test_function(node):
            self.generic_visit(node)
            return

        self.scanned_tests += 1
        func_name = node.name
        func_start = node.lineno
        func_end = getattr(node, "end_lineno", node.lineno)

        func_boundary_modules = self._collect_func_boundaries(node)
        is_boundary_adapter = len(func_boundary_modules) > 0

        mock_assertions = 0
        state_assertions = 0
        mock_operations = 0
        total_operations = 0
        last_mock_line = func_start

        mock_return_values: List[Tuple[Any, int]] = []
        candidate_echo_calls: List[Tuple[List[ast.AST], int]] = []
        candidate_echo_compares: List[Tuple[ast.Compare, int]] = []

        screenshot_existence_checks: List[Tuple[int, str]] = []
        has_vrt_diff_call = False
        local_var_assignments: Dict[str, str] = {}

        local_constants: Dict[str, Any] = {}
        self._current_local_constants: Dict[str, Any] = {}
        for stmt in getattr(node, "body", []):
            if isinstance(stmt, ast.Assign):
                c_val = self._extract_constant_value(stmt.value)
                if c_val is not None:
                    for tgt in stmt.targets:
                        if isinstance(tgt, ast.Name):
                            self._current_local_constants[tgt.id] = c_val
                            local_constants[tgt.id] = c_val
        constant_tautologies: List[Tuple[int, str]] = []

        for subnode in ast.walk(node):
            if subnode is node:
                continue

            if isinstance(subnode, ast.Assign):
                extracted_str = self._extract_path_target(subnode.value, local_var_assignments)
                if extracted_str:
                    for target in subnode.targets:
                        if isinstance(target, ast.Name):
                            local_var_assignments[target.id] = extracted_str

                extracted_val = self._extract_constant_value(subnode.value)
                if extracted_val is not None:
                    for target in subnode.targets:
                        if isinstance(target, ast.Name):
                            local_constants[target.id] = extracted_val
                            self._current_local_constants[target.id] = extracted_val

                if isinstance(subnode.value, ast.ListComp) and isinstance(subnode.value.elt, ast.Call):
                    elt_func = ""
                    if isinstance(subnode.value.elt.func, ast.Name):
                        elt_func = subnode.value.elt.func.id
                    elif isinstance(subnode.value.elt.func, ast.Attribute):
                        elt_func = subnode.value.elt.func.attr
                    if elt_func in {"Mock", "MagicMock", "AsyncMock"}:
                        num_mocks = 1
                        for target in subnode.targets:
                            if isinstance(target, (ast.Tuple, ast.List)):
                                num_mocks = max(num_mocks, len(target.elts))
                        mock_operations += num_mocks
                        total_operations += num_mocks

                for target in subnode.targets:
                    if isinstance(target, ast.Attribute) and target.attr == "return_value":
                        mock_operations += 1
                        val = self._extract_constant_value(subnode.value)
                        if val is not None:
                            mock_return_values.append((val, subnode.lineno))

            elif isinstance(subnode, ast.Call):
                total_operations += 1
                func_id = ""
                if isinstance(subnode.func, ast.Name):
                    func_id = subnode.func.id
                elif isinstance(subnode.func, ast.Attribute):
                    func_id = subnode.func.attr

                if func_id in {"Mock", "MagicMock", "AsyncMock", "create_autospec", "patch"}:
                    mock_operations += 1

                if isinstance(subnode.func, ast.Name):
                    callee = subnode.func.id
                    if (
                        callee
                        and callee[0].isupper()
                        and callee not in JS_BUILTIN_PASCAL_CASE
                        and not callee.endswith("Error")
                        and (
                            callee.endswith("Component")
                            or any(kw.arg in {"props", "children"} for kw in subnode.keywords)
                            or ("component" in func_name.lower())
                            or "Component(" in self.lines[subnode.lineno - 1]
                        )
                    ):
                        if not _is_rule_suppressed("SM002", subnode.lineno, func_start, func_end, self.pragmas):
                            self.smells.append(
                                TestSmell(
                                    file_path=self.file_path,
                                    line_number=subnode.lineno,
                                    rule_id=SmellType.DIRECT_COMPONENT_CALL.value,
                                    severity=SmellSeverity.HARD_REJECTION.value,
                                    message=f"Direct Component call '{callee}(...)' in test without DOM mounting.",
                                    context_snippet=_get_context_snippet(self.lines, subnode.lineno),
                                    test_name=func_name,
                                    remediation="Use DOM mounting utilities (render, mount) rather than direct component invocation.",
                                )
                            )

                for kw in subnode.keywords:
                    if kw.arg == "return_value":
                        mock_operations += 1
                        val = self._extract_constant_value(kw.value)
                        if val is not None:
                            mock_return_values.append((val, subnode.lineno))

                full_call_name = ""
                if isinstance(subnode.func, ast.Name):
                    full_call_name = subnode.func.id
                elif isinstance(subnode.func, ast.Attribute):
                    val_id = subnode.func.value.id if isinstance(subnode.func.value, ast.Name) else ""
                    full_call_name = f"{val_id}.{subnode.func.attr}" if val_id else subnode.func.attr

                if func_id in VRT_DIFF_INDICATORS or full_call_name in VRT_DIFF_INDICATORS or any(
                    full_call_name.endswith(f".{ind}") for ind in VRT_DIFF_INDICATORS
                ):
                    has_vrt_diff_call = True

                if isinstance(subnode.func, ast.Attribute):
                    attr_name = subnode.func.attr
                    if attr_name in PYTHON_MOCK_ASSERT_ATTRS:
                        mock_assertions += 1
                        mock_operations += 1
                        last_mock_line = subnode.lineno

                    elif attr_name in PYTHON_STATE_ASSERT_ATTRS:
                        is_mock_prop_assert = any(self._is_mock_call_inspection(arg) for arg in subnode.args)

                        if is_mock_prop_assert:
                            mock_assertions += 1
                            mock_operations += 1
                            last_mock_line = subnode.lineno
                        elif self._is_trivial_call_assertion(attr_name, subnode.args):
                            try:
                                call_str = ast.unparse(subnode)
                            except Exception:
                                call_str = f"self.{attr_name}(...)"
                            constant_tautologies.append((subnode.lineno, call_str))
                        else:
                            state_assertions += 1
                            for arg in subnode.args:
                                target_file = self._inspect_for_vrt_fake_check(arg, local_var_assignments)
                                if target_file:
                                    screenshot_existence_checks.append((subnode.lineno, target_file))

                        if attr_name in {"assertEqual", "assertDictEqual"}:
                            candidate_echo_calls.append((subnode.args, subnode.lineno))

            elif isinstance(subnode, ast.Assert):
                total_operations += 1
                if self._is_mock_call_inspection(subnode.test):
                    mock_assertions += 1
                    mock_operations += 1
                    last_mock_line = subnode.lineno
                elif self._is_trivial_expression(subnode.test):
                    try:
                        expr_str = ast.unparse(subnode.test)
                    except Exception:
                        expr_str = "trivial assertion"
                    constant_tautologies.append((subnode.lineno, f"assert {expr_str}"))
                else:
                    state_assertions += 1
                    target_file = self._inspect_for_vrt_fake_check(subnode.test, local_var_assignments)
                    if target_file:
                        screenshot_existence_checks.append((subnode.lineno, target_file))
                    if isinstance(subnode.test, ast.Compare):
                        candidate_echo_compares.append((subnode.test, subnode.lineno))

            elif isinstance(subnode, ast.With):
                for item in subnode.items:
                    if isinstance(item.context_expr, ast.Call):
                        call_func = item.context_expr.func
                        call_name = ""
                        if isinstance(call_func, ast.Name):
                            call_name = call_func.id
                        elif isinstance(call_func, ast.Attribute):
                            call_name = call_func.attr
                        if call_name in {"assertRaises", "raises"}:
                            state_assertions += 1

        for echo_args, echo_line in candidate_echo_calls:
            self._check_echo_in_args(echo_args, mock_return_values, echo_line, func_name, func_start, func_end)
        for echo_comp, echo_line in candidate_echo_compares:
            self._check_echo_in_compare(echo_comp, mock_return_values, echo_line, func_name, func_start, func_end)

        # Evaluate SM001: Zero-State Tautology (It == 1.0)
        is_sm001_waived = is_boundary_adapter
        sm001_flagged = False
        if mock_assertions >= 1 and state_assertions == 0:
            if not is_sm001_waived and not _is_rule_suppressed("SM001", last_mock_line, func_start, func_end, self.pragmas):
                self.smells.append(
                    TestSmell(
                        file_path=self.file_path,
                        line_number=last_mock_line,
                        rule_id=SmellType.ZERO_STATE_TAUTOLOGY.value,
                        severity=SmellSeverity.HARD_REJECTION.value,
                        message=(
                            f"Zero-State Tautology (Mock-only tautology) detected (It == 1.0): Test '{func_name}' asserts "
                            f"{mock_assertions} mock call(s) with 0 state/data assertions."
                        ),
                        context_snippet=_get_context_snippet(self.lines, last_mock_line),
                        test_name=func_name,
                        remediation="Add assertions verifying returned values, mutated properties, or persistent data records.",
                        metrics={"mock_assertions": mock_assertions, "state_assertions": state_assertions, "it": 1.0},
                    )
                )
                sm001_flagged = True

        if constant_tautologies and not sm001_flagged:
            first_line, expr_str = constant_tautologies[0]
            if not _is_rule_suppressed("SM001", first_line, func_start, func_end, self.pragmas):
                self.smells.append(
                    TestSmell(
                        file_path=self.file_path,
                        line_number=first_line,
                        rule_id=SmellType.ZERO_STATE_TAUTOLOGY.value,
                        severity=SmellSeverity.HARD_REJECTION.value,
                        message=(
                            f"Zero-State Tautology (zero-state-tautology): constant or identical assertion '{expr_str}' "
                            f"detected in test '{func_name}'."
                        ),
                        context_snippet=_get_context_snippet(self.lines, first_line),
                        test_name=func_name,
                        remediation="Replace constant tautological assertion with genuine assertions verifying returned values or state transitions.",
                        metrics={"mock_assertions": mock_assertions, "state_assertions": state_assertions, "tautology": expr_str},
                    )
                )

        # Evaluate SM003: Fake Visual Regression Tests (Fake VRT)
        if screenshot_existence_checks and not has_vrt_diff_call:
            for check_line, target_file in screenshot_existence_checks:
                if not _is_rule_suppressed("SM003", check_line, func_start, func_end, self.pragmas):
                    self.smells.append(
                        TestSmell(
                            file_path=self.file_path,
                            line_number=check_line,
                            rule_id=SmellType.FAKE_VRT.value,
                            severity=SmellSeverity.HARD_REJECTION.value,
                            message=(
                                f"Fake Visual Regression Test detected: Test '{func_name}' asserts filesystem existence "
                                f"of screenshot '{target_file}' without pixel/image comparison."
                            ),
                            context_snippet=_get_context_snippet(self.lines, check_line),
                            test_name=func_name,
                            remediation="Replace filesystem existence check with real pixel buffer comparison (e.g. toHaveScreenshot, pixelmatch, or image diffing).",
                            metrics={"target_file": target_file},
                        )
                    )

        # Evaluate SM005: Mock Density & Boundary Exemptions
        total_density_ops = max(1, total_operations)
        mock_density = mock_operations / total_density_ops
        if mock_operations >= 3 and mock_density > 0.5:
            if is_boundary_adapter:
                adapter_desc = ", ".join(func_boundary_modules) if func_boundary_modules else "system boundary"
                self.exemptions.append(
                    BoundaryExemptionRecord(
                        file_path=self.file_path,
                        test_name=func_name,
                        reason=f"Waived mock density (Dm={mock_density:.2f}): wraps system boundary adapters ({adapter_desc})",
                        adapter_modules=func_boundary_modules,
                    )
                )
            elif not _is_rule_suppressed("SM005", func_start, func_start, func_end, self.pragmas):
                self.smells.append(
                    TestSmell(
                        file_path=self.file_path,
                        line_number=func_start,
                        rule_id=SmellType.MOCK_DENSITY_WARNING.value,
                        severity=SmellSeverity.WARNING.value,
                        message=(
                            f"High Mock Density detected (Dm={mock_density:.2f}): Test '{func_name}' relies heavily "
                            f"on mocks ({mock_operations} mock operations)."
                        ),
                        context_snippet=_get_context_snippet(self.lines, func_start),
                        test_name=func_name,
                        remediation="Reduce mock coupling by testing through public interfaces or stateful integration tests.",
                        metrics={"mock_operations": mock_operations, "mock_density": mock_density},
                    )
                )

    def _extract_path_target(
        self,
        node: ast.AST,
        local_vars: Optional[Dict[str, str]] = None,
    ) -> str:
        """Recursively extracts a path string, handling literals, names, Path() calls, divisions (/), and chained methods."""
        if local_vars is None:
            local_vars = {}
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return local_vars.get(node.id, node.id)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            left_str = self._extract_path_target(node.left, local_vars)
            right_str = self._extract_path_target(node.right, local_vars)
            return f"{left_str}/{right_str}" if (left_str and right_str) else (right_str or left_str)
        if isinstance(node, ast.Call):
            func_id = node.func.id if isinstance(node.func, ast.Name) else (node.func.attr if isinstance(node.func, ast.Attribute) else "")
            if func_id == "Path":
                return self._extract_path_target(node.args[0], local_vars) if node.args else ""
            if isinstance(node.func, ast.Attribute) and func_id in {"resolve", "absolute", "expanduser", "as_posix"}:
                return self._extract_path_target(node.func.value, local_vars)
        return ""

    def _is_image_or_screenshot_path(self, target_str: str) -> bool:
        if not target_str:
            return False
        target_lower = target_str.lower()
        non_image_exts = {".md", ".txt", ".json", ".py", ".ts", ".js", ".log", ".html", ".csv", ".xml", ".yaml", ".yml"}
        if any(target_lower.endswith(ext) for ext in non_image_exts):
            return False
        is_image_ext = any(target_lower.endswith(ext) for ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp"})
        return is_image_ext or any(kw in target_lower for kw in {"screenshot", "snapshot"})

    def _inspect_for_vrt_fake_check(
        self,
        node: ast.AST,
        local_vars: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """Inspect AST node for Fake VRT assertions (exists/isfile/is_file/st_size/getsize)."""
        if local_vars is None:
            local_vars = {}

        if isinstance(node, ast.Compare):
            for cand in [node.left] + node.comparators:
                res = self._inspect_for_vrt_fake_check(cand, local_vars)
                if res:
                    return res

        if isinstance(node, ast.Attribute) and node.attr in {"st_size", "st_blocks"} and isinstance(node.value, ast.Call):
            call_func = node.value.func
            call_name = call_func.attr if isinstance(call_func, ast.Attribute) else (call_func.id if isinstance(call_func, ast.Name) else "")
            if call_name == "stat":
                if node.value.args:
                    path_target = self._extract_path_target(node.value.args[0], local_vars)
                    if self._is_image_or_screenshot_path(path_target):
                        return path_target or "screenshot"
                elif isinstance(call_func, ast.Attribute):
                    path_target = self._extract_path_target(call_func.value, local_vars)
                    if self._is_image_or_screenshot_path(path_target):
                        return path_target or "screenshot"

        if isinstance(node, ast.Call):
            call_func = node.func
            call_name = call_func.attr if isinstance(call_func, ast.Attribute) else (call_func.id if isinstance(call_func, ast.Name) else "")
            if call_name in {"exists", "isfile", "is_file"}:
                target_str = self._extract_path_target(node.args[0], local_vars) if node.args else (
                    self._extract_path_target(call_func.value, local_vars) if isinstance(call_func, ast.Attribute) else ""
                )
                if self._is_image_or_screenshot_path(target_str):
                    return target_str or "screenshot"
            elif call_name == "getsize" and node.args:
                target_str = self._extract_path_target(node.args[0], local_vars)
                if self._is_image_or_screenshot_path(target_str):
                    return target_str or "screenshot"

        return None

    def _check_echo_in_args(
        self,
        args: List[ast.AST],
        mock_returns: List[Tuple[Any, int]],
        line_number: int,
        func_name: str,
        func_start: int = -1,
        func_end: int = -1,
    ) -> None:
        """Checks if arguments to assertEqual match a mock return value (SM004)."""
        if len(args) < 2 or not mock_returns:
            return
        val1 = self._extract_constant_value(args[0])
        val2 = self._extract_constant_value(args[1])
        for mock_val, _ in mock_returns:
            if not _is_excluded_echo_scalar(mock_val) and (
                (val1 is not None and val1 == mock_val) or (val2 is not None and val2 == mock_val)
            ):
                self._record_echo(line_number, func_name, mock_val, func_start, func_end)
                return
            if isinstance(mock_val, (dict, list, tuple)):
                for leaf_val, leaf_path in _extract_nested_leaf_values(mock_val):
                    if (val1 is not None and val1 == leaf_val) or (val2 is not None and val2 == leaf_val):
                        self._record_echo(line_number, func_name, {leaf_path: leaf_val}, func_start, func_end)
                        return

    def _check_echo_in_compare(
        self,
        compare: ast.Compare,
        mock_returns: List[Tuple[Any, int]],
        line_number: int,
        func_name: str,
        func_start: int = -1,
        func_end: int = -1,
    ) -> None:
        """Checks if a comparison assert matches a mock return value (SM004)."""
        if not mock_returns:
            return
        left_val = self._extract_constant_value(compare.left)
        right_vals = [self._extract_constant_value(c) for c in compare.comparators]
        for mock_val, _ in mock_returns:
            if not _is_excluded_echo_scalar(mock_val):
                if (left_val is not None and left_val == mock_val) or any(
                    rv is not None and rv == mock_val for rv in right_vals
                ):
                    self._record_echo(line_number, func_name, mock_val, func_start, func_end)
                    return
            if isinstance(mock_val, (dict, list, tuple)):
                for leaf_val, leaf_path in _extract_nested_leaf_values(mock_val):
                    if (left_val is not None and left_val == leaf_val) or any(
                        rv is not None and rv == leaf_val for rv in right_vals
                    ):
                        self._record_echo(line_number, func_name, {leaf_path: leaf_val}, func_start, func_end)
                        return

    def _record_echo(
        self,
        line_number: int,
        func_name: str,
        echoed_val: Any,
        func_start: int = -1,
        func_end: int = -1,
    ) -> None:
        f_start = func_start if func_start >= 0 else line_number
        f_end = func_end if func_end >= 0 else line_number
        if not _is_rule_suppressed("SM004", line_number, f_start, f_end, self.pragmas):
            val_repr = str(echoed_val)
            if len(val_repr) > 40:
                val_repr = val_repr[:37] + "..."
            self.smells.append(
                TestSmell(
                    file_path=self.file_path,
                    line_number=line_number,
                    rule_id=SmellType.ECHO_ASSERTION.value,
                    severity=SmellSeverity.WARNING.value,
                    message=(
                        f"Echo Assertion detected: Assertion in '{func_name}' strictly mirrors "
                        f"hardcoded mock return value '{val_repr}'."
                    ),
                    context_snippet=_get_context_snippet(self.lines, line_number),
                    test_name=func_name,
                    remediation="Verify downstream business transformation, state mutation, or edge cases rather than mirroring mock inputs.",
                    metrics={"echoed_value": val_repr},
                )
            )
