# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Static AST Test Smell Linter (Epic #51 Phase 3.1 R1).

Detects, flags, and rejects synthetic, tautological, and fake test implementations:
- SM001: Zero-State Tautologies (It == 1.0) [Hard Rejection]
- SM002: Direct React/Vue Component Function Calls [Hard Rejection]
- SM003: Fake Visual Regression Tests (existence checks without pixel diffs) [Hard Rejection]
- SM004: Echo Assertions (assertions mirroring mock return values) [Actionable Warning]
- SM005: High Mock Density (waived automatically on boundary adapters) [Actionable Warning]

Escape Pragma:
  # agyis: no-smell <reason>
  # agyis: no-smell SM001 <reason>
  // agyis: no-smell <reason>
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# Boundary modules indicating system/adapter tests where high mock density is expected and waived
BOUNDARY_MODULES: Set[str] = {
    "socket",
    "ssl",
    "select",
    "asyncio.open_connection",
    "subprocess",
    "pty",
    "termios",
    "fcntl",
    "docker",
    "docker.models",
    "containerd",
    "paramiko",
    "cryptography",
    "cryptography.hazmat",
    "net",
    "node:net",
    "child_process",
    "node:child_process",
    "dgram",
    "node:dgram",
    "dockerode",
    "ssh2",
}

BOUNDARY_PATH_KEYWORDS: Set[str] = {
    "adapter",
    "boundary",
    "socket",
    "subprocess",
    "docker",
    "remote",
    "pty",
}

ADAPTER_PATTERNS = re.compile(r"(?:Adapter|Socket|Docker|Client|Process)", re.IGNORECASE)

# Standard mock assertion names on Python mock objects
PYTHON_MOCK_ASSERT_ATTRS: Set[str] = {
    "assert_called",
    "assert_called_once",
    "assert_called_with",
    "assert_called_once_with",
    "assert_any_call",
    "assert_has_calls",
    "assert_not_called",
    # AsyncMock assertions (Python 3.8+)
    "assert_awaited",
    "assert_awaited_once",
    "assert_awaited_with",
    "assert_awaited_once_with",
    "assert_any_await",
    "assert_has_awaits",
    "assert_not_awaited",
}

# Standard mock inspection property/call attributes
PYTHON_MOCK_PROP_ATTRS: Set[str] = {
    "called",
    "call_count",
    "mock_calls",
    "call_args",
    "call_args_list",
    "method_calls",
}

# Standard unittest assertion names
PYTHON_STATE_ASSERT_ATTRS: Set[str] = {
    "assertEqual",
    "assertNotEqual",
    "assertTrue",
    "assertFalse",
    "assertIn",
    "assertNotIn",
    "assertIs",
    "assertIsNot",
    "assertIsNone",
    "assertIsNotNone",
    "assertIsInstance",
    "assertNotIsInstance",
    "assertGreater",
    "assertGreaterEqual",
    "assertLess",
    "assertLessEqual",
    "assertAlmostEqual",
    "assertNotAlmostEqual",
    "assertRegex",
    "assertNotRegex",
    "assertDictEqual",
    "assertListEqual",
    "assertSetEqual",
    "assertSequenceEqual",
    "assertRaises",
    "assertRaisesRegex",
    "assertWarns",
    "assertWarnsRegex",
    "assertLogs",
    "assertCountEqual",
    "assertMultiLineEqual",
}

# Trivial scalar values excluded from echo assertion warnings
EXCLUDED_ECHO_SCALARS: Set[Any] = {True, False, 0, 1, "", None}


def _is_excluded_echo_scalar(val: Any) -> bool:
    """Returns True if val is a trivial scalar {True, False, 0, 1, '', None}."""
    if val is None or val is True or val is False:
        return True
    if isinstance(val, (int, float)) and val in (0, 1):
        return True
    if isinstance(val, str) and val == "":
        return True
    return False


def _extract_nested_leaf_values(val: Any) -> List[Tuple[Any, str]]:
    """
    Recursively extracts leaf scalar values from nested dicts, lists, and tuples.
    Returns list of (leaf_value, context_path).
    Filters out trivial scalar values ({True, False, 0, 1, '', None}).
    """
    leaves: List[Tuple[Any, str]] = []

    def _recurse(current: Any, path: str) -> None:
        if isinstance(current, dict):
            for k, v in current.items():
                new_path = f"{path}.{k}" if path else str(k)
                _recurse(v, new_path)
        elif isinstance(current, (list, tuple)):
            for idx, item in enumerate(current):
                new_path = f"{path}[{idx}]" if path else f"[{idx}]"
                _recurse(item, new_path)
        else:
            if not _is_excluded_echo_scalar(current):
                leaves.append((current, path or str(current)))

    _recurse(val, "")
    return leaves

# Visual regression comparison function / matcher indicators
VRT_DIFF_INDICATORS: Set[str] = {
    "pixelmatch",
    "assert_images_equal",
    "diff_images",
    "ImageChops",
    "difference",
    "toMatchSnapshot",
    "toHaveScreenshot",
    "toMatchImageSnapshot",
    "matchImageSnapshot",
    "cy.matchImageSnapshot",
    "read_bytes",
}

# Standard JS builtins in PascalCase that are not React/Vue components
JS_BUILTIN_PASCAL_CASE: Set[str] = {
    "Array",
    "Object",
    "Function",
    "Boolean",
    "Number",
    "String",
    "Symbol",
    "BigInt",
    "Error",
    "TypeError",
    "RangeError",
    "SyntaxError",
    "ReferenceError",
    "URIError",
    "EvalError",
    "RegExp",
    "Date",
    "Promise",
    "Map",
    "Set",
    "WeakMap",
    "WeakSet",
    "ArrayBuffer",
    "SharedArrayBuffer",
    "DataView",
    "Int8Array",
    "Uint8Array",
    "Uint8ClampedArray",
    "Int16Array",
    "Uint16Array",
    "Int32Array",
    "Uint32Array",
    "Float32Array",
    "Float64Array",
    "BigInt64Array",
    "BigUint64Array",
    "URL",
    "URLSearchParams",
    "JSON",
    "Math",
    "Reflect",
    "Proxy",
    "Intl",
    "Buffer",
    "Path",
    "File",
    "Blob",
    "FormData",
    "Headers",
    "Request",
    "Response",
    "AbortController",
    "Event",
    "CustomEvent",
    "EventTarget",
    "Describe",
    "Test",
    "It",
    "Expect",
    "BeforeEach",
    "AfterEach",
    "BeforeAll",
    "AfterAll",
    "Suite",
}


class SeverityStr(str):
    """Case-insensitive string representation for severity matching both 'WARNING' and 'warning', 'HARD_REJECTION', 'ERROR', 'REJECT', and 'hard_reject'."""

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            s1 = str(self).lower()
            s2 = str(other).lower()
            hard_set = {"error", "hard_rejection", "reject", "hard_reject"}
            if s1 in hard_set and s2 in hard_set:
                return True
            return s1 == s2
        return super().__eq__(other)

    def __hash__(self) -> int:
        s = str(self).lower()
        if s in {"error", "hard_rejection", "reject", "hard_reject"}:
            return hash("error")
        return hash(s)

    def upper(self) -> SeverityStr:
        return SeverityStr(super().upper())

    def lower(self) -> SeverityStr:
        return SeverityStr(super().lower())


class RuleIdStr(str):
    """String representation allowing bidirectional equality between SM00x and hyphenated names."""
    _MAP = {
        "sm001": "zero-state-tautology",
        "sm002": "direct-component-call",
        "sm003": "fake-vrt",
        "sm004": "echo-assertion",
        "sm005": "mock-density-warning",
        "zero-state-tautology": "sm001",
        "direct-component-call": "sm002",
        "fake-vrt": "sm003",
        "echo-assertion": "sm004",
        "mock-density-warning": "sm005",
    }

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            s1 = self.lower().replace("_", "-")
            s2 = other.lower().replace("_", "-")
            if s1 == s2:
                return True
            if self._MAP.get(s1) == s2 or self._MAP.get(s2) == s1:
                return True
        return super().__eq__(other)

    def __hash__(self) -> int:
        s = self.lower().replace("_", "-")
        canonical = self._MAP.get(s, s)
        return hash(canonical)


class SmellSeverity(str, Enum):
    """Severity levels for detected test smells."""
    HARD_REJECTION = SeverityStr("HARD_REJECTION")
    WARNING = SeverityStr("WARNING")
    EXEMPTION = SeverityStr("EXEMPTION")


class SmellType(str, Enum):
    """Standardized smell rule identifiers."""
    ZERO_STATE_TAUTOLOGY = RuleIdStr("SM001")
    DIRECT_COMPONENT_CALL = RuleIdStr("SM002")
    FAKE_VRT = RuleIdStr("SM003")
    ECHO_ASSERTION = RuleIdStr("SM004")
    MOCK_DENSITY_WARNING = RuleIdStr("SM005")
    BOUNDARY_EXEMPT = RuleIdStr("BOUNDARY_EXEMPT")


@dataclass
class TestSmell:
    """Represents a single detected test smell violation."""
    file_path: str
    line_number: int
    rule_id: str
    severity: str  # "hard_rejection" | "warning" | "ERROR"
    message: str
    context_snippet: str = ""
    test_name: str = ""
    remediation: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.rule_id, RuleIdStr):
            self.rule_id = RuleIdStr(self.rule_id)
        if not isinstance(self.severity, SeverityStr):
            self.severity = SeverityStr(self.severity)

    @property
    def smell_type(self) -> str:
        return self.rule_id

    @property
    def code_snippet(self) -> str:
        return self.context_snippet

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file_path,
            "file_path": self.file_path,
            "line": self.line_number,
            "line_number": self.line_number,
            "test": self.test_name,
            "rule_id": self.rule_id,
            "smell_type": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "remediation": self.remediation,
            "context_snippet": self.context_snippet,
            "code_snippet": self.context_snippet,
            "metrics": self.metrics,
        }


# Backwards compatibility alias
TestSmellIssue = TestSmell


@dataclass
class BoundaryExemptionRecord:
    """Record of a waived mock density warning due to system boundary adaptation."""
    file_path: str
    test_name: str
    reason: str
    adapter_modules: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file_path,
            "test": self.test_name,
            "reason": self.reason,
            "adapters": self.adapter_modules,
        }


@dataclass
class SmellAuditReport:
    """Aggregated audit report containing smells and exemptions."""
    workspace_root: str = ""
    target_path: Optional[str] = None
    scanned_files: int = 0
    scanned_tests: int = 0
    hard_rejections: List[TestSmell] = field(default_factory=list)
    warnings: List[TestSmell] = field(default_factory=list)
    exemptions: List[BoundaryExemptionRecord] = field(default_factory=list)
    passed: bool = True

    @property
    def total_files_scanned(self) -> int:
        return self.scanned_files

    @property
    def hard_rejects_count(self) -> int:
        return len(self.hard_rejections)

    @property
    def warnings_count(self) -> int:
        return len(self.warnings)

    @property
    def issues(self) -> List[TestSmell]:
        return self.hard_rejections + self.warnings

    def print_summary(self) -> None:
        print_ansi_smell_report(self)

    def to_dict(self) -> Dict[str, Any]:
        summary = {
            "scanned_files": self.scanned_files,
            "scanned_tests": self.scanned_tests,
            "hard_rejections_count": len(self.hard_rejections),
            "warnings_count": len(self.warnings),
            "exemptions_count": len(self.exemptions),
            "passed": self.passed,
        }
        if not self.passed and self.scanned_files == 0 and self.target_path:
            summary["error"] = f"Target test path does not exist: {self.target_path}"

        return {
            "workspace_root": self.workspace_root,
            "target_path": self.target_path,
            "total_files_scanned": self.scanned_files,
            "hard_rejects_count": len(self.hard_rejections),
            "warnings_count": len(self.warnings),
            "issues": [i.to_dict() for i in self.issues],
            "passed": self.passed,
            "summary": summary,
            "hard_rejections": [r.to_dict() for r in self.hard_rejections],
            "warnings": [w.to_dict() for w in self.warnings],
            "exemptions": [e.to_dict() for e in self.exemptions],
        }


TestSmellReport = SmellAuditReport


# Regex for escape pragmas:
# # agyis: no-smell [rule_id] [reason]
# // agyis: no-smell [rule_id] [reason]
PRAGMA_PATTERN = re.compile(
    r'(?:#|//|/\*)\s*agyis:\s*no-smell(?:\s+([A-Za-z0-9_-]+))?(?:\s+(.*?))?(?:\*/)?$',
    re.IGNORECASE,
)


STRICT_RULE_ID_PATTERN = re.compile(r"^SM\d{3}$", re.IGNORECASE)
MALFORMED_RULE_PATTERN = re.compile(r"^SM[-_0-9]\S*", re.IGNORECASE)


def _extract_pragmas(lines: List[str]) -> Dict[int, Set[str]]:
    """
    Extracts inline and block pragmas from source code lines.
    Returns map of 1-based line number -> set of waived rule IDs (or {'*'} for all).
    """
    pragmas: Dict[int, Set[str]] = {}
    for idx, line in enumerate(lines, start=1):
        match = PRAGMA_PATTERN.search(line)
        if match:
            first_token = (match.group(1) or "").strip()
            if not first_token:
                # No token given: '# agyis: no-smell' -> waives all rules
                pragmas[idx] = {"*"}
            elif STRICT_RULE_ID_PATTERN.match(first_token):
                # Valid rule ID: e.g. 'SM001'
                pragmas[idx] = {first_token.upper()}
            elif MALFORMED_RULE_PATTERN.match(first_token):
                # Malformed / unrecognized rule candidate: e.g. 'SM-001', 'SM01', 'SM_001'
                # Do NOT silently waive all rules! Waive nothing.
                pass
            else:
                # First token is part of natural language reason: 'Smoke', 'Small', 'intentional'
                # Developer provided a reason without a rule ID -> waives all rules
                pragmas[idx] = {"*"}
    return pragmas


def _is_rule_suppressed(
    rule_id: str,
    line_number: int,
    func_start: int,
    func_end: int,
    pragmas: Dict[int, Set[str]],
) -> bool:
    """Checks whether a rule is suppressed for a given line or enclosing function."""
    # Check exact line
    if line_number in pragmas:
        rules = pragmas[line_number]
        if "*" in rules or rule_id in rules:
            return True

    # Check preceding line before function (e.g. comment above def)
    for pre_line in (func_start - 1, func_start):
        if pre_line in pragmas:
            rules = pragmas[pre_line]
            if "*" in rules or rule_id in rules:
                return True

    # Check anywhere inside function body
    for line in range(func_start, func_end + 1):
        if line in pragmas:
            rules = pragmas[line]
            if "*" in rules or rule_id in rules:
                return True

    return False


def _get_context_snippet(lines: List[str], line_number: int) -> str:
    """Returns a short 1-to-3 line context snippet for a report."""
    if not lines or line_number < 1 or line_number > len(lines):
        return ""
    start = max(1, line_number - 1)
    end = min(len(lines), line_number + 1)
    snippet_lines = [f"{i}: {lines[i - 1].strip()}" for i in range(start, end + 1)]
    return "\n".join(snippet_lines)


class PythonTestSmellVisitor(ast.NodeVisitor):
    """
    AST Visitor auditing Python test functions for synthetic test smells.
    """

    def __init__(self, file_path: str, lines: List[str], pragmas: Dict[int, Set[str]]):
        self.file_path = file_path
        self.lines = lines
        self.pragmas = pragmas
        self.smells: List[TestSmell] = []
        self.exemptions: List[BoundaryExemptionRecord] = []
        self.scanned_tests = 0

        # Boundary symbols tracked from file-level and class-level imports
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
                # Also index module and base package names
                self.boundary_symbols[node.module] = node.module
                self.boundary_symbols[base_mod] = base_mod
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Inspects class-level patch decorators and class name for boundary adapters."""
        prev_class_boundary = list(self.class_boundary_modules)
        if ADAPTER_PATTERNS.search(node.name) or any(kw in node.name.lower() for kw in BOUNDARY_PATH_KEYWORDS):
            self.class_boundary_modules.append(f"class:{node.name}")
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                for arg in decorator.args:
                    val = self._extract_constant_value(arg)
                    if isinstance(val, str):
                        for mod in BOUNDARY_MODULES:
                            if val == mod or val.startswith(f"{mod}."):
                                self.class_boundary_modules.append(f"patch:{mod}")
        self.generic_visit(node)
        self.class_boundary_modules = prev_class_boundary

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._audit_test_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._audit_test_function(node)

    def _is_test_function(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> bool:
        if node.name.startswith("test_") or node.name.endswith("_test"):
            return True
        return False

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
        """
        Determines if an expression is inspecting mock call properties or invocations.

        Handles:
        - Attributes: m.called, m.call_count, m.mock_calls, m.call_args, m.call_args_list, m.call_args.args
        - Length calls: len(m.mock_calls), len(m.call_args_list), len(m.method_calls)
        - Subscripts: m.mock_calls[0], m.call_args[0], m.call_args.kwargs['id']
        - Unary ops: not m.called
        - Comparisons: len(m.mock_calls) == 1, m.call_args is not None, m.call_count > 0
        """
        if isinstance(node, ast.Attribute):
            if node.attr in PYTHON_MOCK_PROP_ATTRS:
                return True
            # Support nested attributes like m.call_args.args
            return self._is_mock_call_inspection(node.value)

        if isinstance(node, ast.Call):
            # len(m.mock_calls), len(m.call_args_list)
            if isinstance(node.func, ast.Name) and node.func.id == "len" and node.args:
                return self._is_mock_call_inspection(node.args[0])
            # Direct mock assertion method call if appearing in expression
            if isinstance(node.func, ast.Attribute) and node.func.attr in PYTHON_MOCK_ASSERT_ATTRS:
                return True
            return False

        if isinstance(node, ast.Subscript):
            return self._is_mock_call_inspection(node.value)

        if isinstance(node, ast.UnaryOp):
            return self._is_mock_call_inspection(node.operand)

        if isinstance(node, ast.Compare):
            if self._is_mock_call_inspection(node.left):
                return True
            return any(self._is_mock_call_inspection(comp) for comp in node.comparators)

        return False

    def _is_literal_constant(self, node: ast.AST) -> bool:
        """Determines if an AST node is a literal constant or container of constants."""
        if isinstance(node, ast.Constant):
            return True
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return all(self._is_literal_constant(elt) for elt in node.elts)
        if isinstance(node, ast.Dict):
            return all(
                (k is not None and self._is_literal_constant(k)) and self._is_literal_constant(v)
                for k, v in zip(node.keys, node.values)
            )
        if isinstance(node, ast.UnaryOp):
            return self._is_literal_constant(node.operand)
        return False

    def _is_trivial_expression(self, node: ast.AST) -> bool:
        """
        Determines if an assert expression is a trivial constant or comparison of constants.

        Examples:
        - assert True, assert False, assert 1, assert "ok"
        - assert 1 == 1, assert "a" == "a", assert True is True, assert 1 != 2
        - assert 1 + 1 == 2
        """
        if self._is_literal_constant(node):
            return True
        if isinstance(node, ast.Compare):
            if self._is_literal_constant(node.left) and all(
                self._is_literal_constant(comp) for comp in node.comparators
            ):
                return True
            if any(
                isinstance(op, (ast.Eq, ast.Is, ast.LtE, ast.GtE)) and ast.dump(node.left) == ast.dump(comp)
                for op, comp in zip(node.ops, node.comparators)
            ):
                return True
            return False
        if isinstance(node, ast.BoolOp):
            return all(self._is_trivial_expression(v) for v in node.values)
        if isinstance(node, ast.UnaryOp):
            return self._is_trivial_expression(node.operand)
        return False

    def _is_trivial_call_assertion(self, attr_name: str, args: List[ast.AST]) -> bool:
        """
        Determines if a unittest assert call is asserting strictly on literal constants.

        Examples:
        - self.assertTrue(True), self.assertTrue(1 == 1), self.assertFalse(False)
        - self.assertEqual(1, 1), self.assertEqual("a", "a"), self.assertIs(True, True)
        - self.assertIsInstance(1, int)
        """
        if not args:
            return True

        if attr_name in {"assertTrue", "assertFalse", "assertIsNone", "assertIsNotNone"}:
            return self._is_trivial_expression(args[0])

        if attr_name in {"assertIsInstance", "assertNotIsInstance"}:
            # Trivial only if the subject value itself is a literal constant (e.g. assertIsInstance(1, int))
            return self._is_literal_constant(args[0])

        if len(args) >= 2:
            return self._is_trivial_expression(args[0]) and self._is_trivial_expression(args[1])

        return False

    def _audit_test_function(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> None:
        if not self._is_test_function(node):
            self.generic_visit(node)
            return

        self.scanned_tests += 1
        func_name = node.name
        func_start = node.lineno
        func_end = getattr(node, "end_lineno", node.lineno)

        # 1. Determine boundary adapter status strictly for this test function
        func_boundary_modules: List[str] = list(self.class_boundary_modules)
        stem = Path(self.file_path).stem
        if ADAPTER_PATTERNS.search(stem) or any(kw in str(self.file_path).lower() for kw in BOUNDARY_PATH_KEYWORDS):
            func_boundary_modules.append(f"file:{stem}")

        # Inspect function-level patch decorators: @patch("subprocess.run"), @patch("socket.socket")
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                for arg in decorator.args:
                    val = self._extract_constant_value(arg)
                    if isinstance(val, str):
                        for mod in BOUNDARY_MODULES:
                            if val == mod or val.startswith(f"{mod}."):
                                patch_desc = f"patch:{mod}"
                                if patch_desc not in func_boundary_modules:
                                    func_boundary_modules.append(patch_desc)

                # @patch.object(subprocess, "run") or @patch.object(socket, ...)
                if isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "object" and decorator.args:
                    first_arg = decorator.args[0]
                    if isinstance(first_arg, ast.Name) and first_arg.id in self.boundary_symbols:
                        mod_ref = self.boundary_symbols[first_arg.id]
                        patch_desc = f"patch.object:{mod_ref}"
                        if patch_desc not in func_boundary_modules:
                            func_boundary_modules.append(patch_desc)

        # Inspect function statements for boundary context managers and symbol usage
        for subnode in ast.walk(node):
            if subnode is node:
                continue

            # Context managers: with patch("subprocess.run") as ...
            if isinstance(subnode, ast.With):
                for item in subnode.items:
                    if isinstance(item.context_expr, ast.Call):
                        call = item.context_expr
                        for arg in call.args:
                            val = self._extract_constant_value(arg)
                            if isinstance(val, str):
                                for mod in BOUNDARY_MODULES:
                                    if val == mod or val.startswith(f"{mod}."):
                                        patch_desc = f"patch:{mod}"
                                        if patch_desc not in func_boundary_modules:
                                            func_boundary_modules.append(patch_desc)
                        if isinstance(call.func, ast.Attribute) and call.func.attr == "object" and call.args:
                            first_arg = call.args[0]
                            if isinstance(first_arg, ast.Name) and first_arg.id in self.boundary_symbols:
                                mod_ref = self.boundary_symbols[first_arg.id]
                                patch_desc = f"patch.object:{mod_ref}"
                                if patch_desc not in func_boundary_modules:
                                    func_boundary_modules.append(patch_desc)

            # References to imported boundary symbols: subprocess.run, socket.socket, Popen
            elif isinstance(subnode, ast.Name) and subnode.id in self.boundary_symbols:
                mod_name = self.boundary_symbols[subnode.id]
                if mod_name not in func_boundary_modules:
                    func_boundary_modules.append(mod_name)

            # Function-level imports
            elif isinstance(subnode, ast.Import):
                for alias in subnode.names:
                    base_mod = alias.name.split(".")[0]
                    if base_mod in BOUNDARY_MODULES or alias.name in BOUNDARY_MODULES:
                        if alias.name not in func_boundary_modules:
                            func_boundary_modules.append(alias.name)
            elif isinstance(subnode, ast.ImportFrom):
                if subnode.module:
                    base_mod = subnode.module.split(".")[0]
                    if base_mod in BOUNDARY_MODULES or subnode.module in BOUNDARY_MODULES:
                        if subnode.module not in func_boundary_modules:
                            func_boundary_modules.append(subnode.module)

        is_boundary_adapter = len(func_boundary_modules) > 0

        # Metrics for SM001 & SM005
        mock_assertions = 0
        state_assertions = 0
        mock_operations = 0
        total_operations = 0
        last_mock_line = func_start

        # Storage for Echo Assertions (SM004)
        mock_return_values: List[Tuple[Any, int]] = []
        candidate_echo_calls: List[Tuple[List[ast.AST], int]] = []
        candidate_echo_compares: List[Tuple[ast.Compare, int]] = []

        # Storage for Fake VRT (SM003)
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

        # Collect internal statements and expressions
        for subnode in ast.walk(node):
            if subnode is node:
                continue

            # Track variable assignments for path/screenshot tracking and local constants
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

            # Mocks created or patched
            elif isinstance(subnode, ast.Call):
                total_operations += 1
                func_id = ""
                if isinstance(subnode.func, ast.Name):
                    func_id = subnode.func.id
                elif isinstance(subnode.func, ast.Attribute):
                    func_id = subnode.func.attr

                if func_id in {"Mock", "MagicMock", "AsyncMock", "create_autospec", "patch"}:
                    mock_operations += 1

                # Check for direct Component calls in Python (SM002)
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

                # Check keyword arguments for return_value in Mock(return_value=...)
                for kw in subnode.keywords:
                    if kw.arg == "return_value":
                        mock_operations += 1
                        val = self._extract_constant_value(kw.value)
                        if val is not None:
                            mock_return_values.append((val, subnode.lineno))

                # Check if this call is an authentic VRT diff call
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

                # Check mock assertion calls
                if isinstance(subnode.func, ast.Attribute):
                    attr_name = subnode.func.attr
                    if attr_name in PYTHON_MOCK_ASSERT_ATTRS:
                        mock_assertions += 1
                        mock_operations += 1
                        last_mock_line = subnode.lineno

                    elif attr_name in PYTHON_STATE_ASSERT_ATTRS:
                        # Check if unittest assert is asserting strictly on mock call properties
                        # e.g. self.assertEqual(len(m.mock_calls), 1) or self.assertIsNotNone(m.call_args)
                        is_mock_prop_assert = any(self._is_mock_call_inspection(arg) for arg in subnode.args)

                        if is_mock_prop_assert:
                            mock_assertions += 1
                            mock_operations += 1
                            last_mock_line = subnode.lineno
                        elif self._is_trivial_call_assertion(attr_name, subnode.args):
                            # Trivial literal assertion (e.g. self.assertTrue(True), self.assertEqual(1, 1))
                            # Exclude from state_assertions to prevent SM001 evasion
                            pass
                        else:
                            state_assertions += 1

                            # Check for fake VRT inside unittest assertion:
                            for arg in subnode.args:
                                target_file = self._inspect_for_vrt_fake_check(arg, local_var_assignments)
                                if target_file:
                                    screenshot_existence_checks.append((subnode.lineno, target_file))

                        # Defer echo assertion check until all mock_return_values are gathered
                        if attr_name in {"assertEqual", "assertDictEqual"}:
                            candidate_echo_calls.append((subnode.args, subnode.lineno))

            # Check standard assert statements
            elif isinstance(subnode, ast.Assert):
                total_operations += 1
                if self._is_mock_call_inspection(subnode.test):
                    mock_assertions += 1
                    mock_operations += 1
                    last_mock_line = subnode.lineno
                elif self._is_trivial_expression(subnode.test):
                    # Trivial assertion (e.g. assert True, assert 1 == 1)
                    # Exclude from state_assertions to prevent SM001 evasion
                    try:
                        expr_str = ast.unparse(subnode.test)
                    except Exception:
                        expr_str = "trivial assertion"
                    constant_tautologies.append((subnode.lineno, f"assert {expr_str}"))
                else:
                    state_assertions += 1

                    # Check fake VRT in assert os.path.exists(...) or assert os.stat(...).st_size > 0
                    target_file = self._inspect_for_vrt_fake_check(subnode.test, local_var_assignments)
                    if target_file:
                        screenshot_existence_checks.append((subnode.lineno, target_file))

                    # Defer echo assertion check until all mock_return_values are gathered
                    if isinstance(subnode.test, ast.Compare):
                        candidate_echo_compares.append((subnode.test, subnode.lineno))

            # Check with self.assertRaises(...) / pytest.raises(...)
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

        # Check deferred candidate echo assertions with the complete list of mock_return_values
        for echo_args, echo_line in candidate_echo_calls:
            self._check_echo_in_args(echo_args, mock_return_values, echo_line, func_name)
        for echo_comp, echo_line in candidate_echo_compares:
            self._check_echo_in_compare(echo_comp, mock_return_values, echo_line, func_name)

        # -------------------------------------------------------------
        # Evaluate SM001: Zero-State Tautology (It == 1.0)
        # -------------------------------------------------------------
        is_socket_adapter = any("socket" in m.lower() and "adapter" in m.lower() for m in func_boundary_modules)
        is_sm001_waived = is_socket_adapter
        if mock_assertions >= 1 and state_assertions == 0:
            if not is_sm001_waived:
                if not _is_rule_suppressed("SM001", last_mock_line, func_start, func_end, self.pragmas):
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
        elif mock_assertions == 0 and state_assertions == 0 and constant_tautologies:
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
                            f"detected in test '{func_name}' with 0 genuine state assertions."
                        ),
                        context_snippet=_get_context_snippet(self.lines, first_line),
                        test_name=func_name,
                        remediation="Replace constant tautological assertion with genuine assertions verifying returned values or state transitions.",
                        metrics={"mock_assertions": 0, "state_assertions": 0, "tautology": expr_str},
                    )
                )

        # -------------------------------------------------------------
        # Evaluate SM003: Fake Visual Regression Tests (Fake VRT)
        # -------------------------------------------------------------
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

        # -------------------------------------------------------------
        # Evaluate SM005: Mock Density & Boundary Exemptions
        # -------------------------------------------------------------
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
            else:
                if not _is_rule_suppressed("SM005", func_start, func_start, func_end, self.pragmas):
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

        # 1. String constant: "screen.png"
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value

        # 2. Variable name: screenshot_path
        if isinstance(node, ast.Name):
            return local_vars.get(node.id, node.id)

        # 3. Path division: Path("out") / "screen.png" or dir / "screen.png"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            left_str = self._extract_path_target(node.left, local_vars)
            right_str = self._extract_path_target(node.right, local_vars)
            if left_str and right_str:
                return f"{left_str}/{right_str}"
            return right_str or left_str

        # 4. Calls: Path("screen.png"), path.resolve(), path.absolute()
        if isinstance(node, ast.Call):
            func_id = ""
            if isinstance(node.func, ast.Name):
                func_id = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_id = node.func.attr

            if func_id == "Path":
                if node.args:
                    return self._extract_path_target(node.args[0], local_vars)
                return ""

            # Chained method calls like .resolve(), .absolute(), .expanduser()
            if isinstance(node.func, ast.Attribute) and func_id in {
                "resolve",
                "absolute",
                "expanduser",
                "as_posix",
            }:
                return self._extract_path_target(node.func.value, local_vars)

        return ""

    def _is_image_or_screenshot_path(self, target_str: str) -> bool:
        if not target_str:
            return False
        target_lower = target_str.lower()
        non_image_exts = {".md", ".txt", ".json", ".py", ".ts", ".js", ".log", ".html", ".csv", ".xml", ".yaml", ".yml"}
        if any(target_lower.endswith(ext) for ext in non_image_exts):
            return False
        is_image_ext = any(target_lower.endswith(ext) for ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".svg"})
        is_vrt_name = any(kw in target_lower for kw in {"screenshot", "snapshot"})
        return is_image_ext or is_vrt_name

    def _inspect_for_vrt_fake_check(
        self,
        node: ast.AST,
        local_vars: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """
        Inspects an AST node for Fake VRT assertions:
        - os.path.exists / isfile
        - Path.exists / is_file
        - os.stat(...).st_size > 0 / Path.stat().st_size > 0
        - os.path.getsize(...) > 0
        """
        if local_vars is None:
            local_vars = {}

        # Case 1: Comparison node: e.g. os.stat('screen.png').st_size > 0, os.path.exists('screen.png') == True
        if isinstance(node, ast.Compare):
            candidates = [node.left] + node.comparators
            for cand in candidates:
                res = self._inspect_for_vrt_fake_check(cand, local_vars)
                if res:
                    return res

        # Case 2: Attribute access: e.g. os.stat('screen.png').st_size, path.stat().st_size
        if isinstance(node, ast.Attribute) and node.attr in {"st_size", "st_blocks"}:
            if isinstance(node.value, ast.Call):
                call_func = node.value.func
                call_name = (
                    call_func.attr
                    if isinstance(call_func, ast.Attribute)
                    else (call_func.id if isinstance(call_func, ast.Name) else "")
                )
                if call_name == "stat":
                    # os.stat('screen.png') -> path is in args[0]
                    if node.value.args:
                        path_target = self._extract_path_target(node.value.args[0], local_vars)
                        if self._is_image_or_screenshot_path(path_target):
                            return path_target or "screenshot"
                    # path.stat() -> path is in func.value
                    elif isinstance(call_func, ast.Attribute):
                        path_target = self._extract_path_target(call_func.value, local_vars)
                        if self._is_image_or_screenshot_path(path_target):
                            return path_target or "screenshot"

        # Case 3: Call node: exists(), isfile(), is_file(), getsize()
        if isinstance(node, ast.Call):
            call_func = node.func
            call_name = (
                call_func.attr
                if isinstance(call_func, ast.Attribute)
                else (call_func.id if isinstance(call_func, ast.Name) else "")
            )

            # 3A: File existence check: os.path.exists(path), path.exists()
            if call_name in {"exists", "isfile", "is_file"}:
                target_str = ""
                if node.args:
                    target_str = self._extract_path_target(node.args[0], local_vars)
                elif isinstance(call_func, ast.Attribute):
                    target_str = self._extract_path_target(call_func.value, local_vars)

                if self._is_image_or_screenshot_path(target_str):
                    return target_str or "screenshot"

            # 3B: Size check via os.path.getsize(path)
            elif call_name == "getsize":
                if node.args:
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
    ) -> None:
        """Checks if arguments to assertEqual match a mock return value (SM004)."""
        if len(args) < 2 or not mock_returns:
            return

        val1 = self._extract_constant_value(args[0])
        val2 = self._extract_constant_value(args[1])

        for mock_val, _ in mock_returns:
            # Direct match (filter out trivial scalars like True, False, 0, 1, "")
            if not _is_excluded_echo_scalar(mock_val):
                if (val1 is not None and val1 == mock_val) or (val2 is not None and val2 == mock_val):
                    self._record_echo(line_number, func_name, mock_val)
                    return

            # Sub-property and nested leaf match for dicts, lists, tuples
            if isinstance(mock_val, (dict, list, tuple)):
                leaves = _extract_nested_leaf_values(mock_val)
                for leaf_val, leaf_path in leaves:
                    if (val1 is not None and val1 == leaf_val) or (val2 is not None and val2 == leaf_val):
                        self._record_echo(line_number, func_name, {leaf_path: leaf_val})
                        return

    def _check_echo_in_compare(
        self,
        compare: ast.Compare,
        mock_returns: List[Tuple[Any, int]],
        line_number: int,
        func_name: str,
    ) -> None:
        """Checks if a comparison assert matches a mock return value (SM004)."""
        if not mock_returns:
            return
        left_val = self._extract_constant_value(compare.left)
        right_vals = [self._extract_constant_value(c) for c in compare.comparators]

        for mock_val, _ in mock_returns:
            # Direct match (filter out trivial scalars)
            if not _is_excluded_echo_scalar(mock_val):
                if left_val is not None and left_val == mock_val:
                    self._record_echo(line_number, func_name, mock_val)
                    return
                for rv in right_vals:
                    if rv is not None and rv == mock_val:
                        self._record_echo(line_number, func_name, mock_val)
                        return

            # Sub-property and nested leaf match
            if isinstance(mock_val, (dict, list, tuple)):
                leaves = _extract_nested_leaf_values(mock_val)
                for leaf_val, leaf_path in leaves:
                    if (left_val is not None and left_val == leaf_val) or any(
                        rv is not None and rv == leaf_val for rv in right_vals
                    ):
                        self._record_echo(line_number, func_name, {leaf_path: leaf_val})
                        return

    def _record_echo(self, line_number: int, func_name: str, echoed_val: Any) -> None:
        if not _is_rule_suppressed("SM004", line_number, line_number, line_number, self.pragmas):
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


class TSJSTestSmellScanner:
    """
    Fast lexical and AST-like scanner auditing TypeScript and JavaScript test suites.
    """

    def __init__(self, file_path: str, content: str):
        self.file_path = file_path
        self.content = content
        self.lines = content.splitlines()
        self.pragmas = _extract_pragmas(self.lines)
        self.smells: List[TestSmell] = []
        self.exemptions: List[BoundaryExemptionRecord] = []
        self.scanned_tests = 0

    def scan(self) -> Tuple[List[TestSmell], List[BoundaryExemptionRecord], int]:
        """Executes lexical analysis on the test file."""
        # 1. Boundary inspection from imports or file path
        boundary_modules = []
        for kw in BOUNDARY_PATH_KEYWORDS:
            if kw in self.file_path.lower():
                boundary_modules.append(f"path:{kw}")

        for mod in BOUNDARY_MODULES:
            if f"'{mod}'" in self.content or f'"{mod}"' in self.content or f"require('{mod}')" in self.content:
                boundary_modules.append(mod)

        # 2. Extract test/it blocks
        # Regex captures:
        # - it(...) / test(...) / xit(...) / xtest(...) / fit(...)
        # - execution modifiers: .only, .skip, .todo, .concurrent, .failing
        # - parameterized tests: .each(...) or .each`table`
        # - callbacks: () => {, (done) => {, done => {, function() {, async function(done) {, function name() {
        test_block_pattern = re.compile(
            r'\b(?:it|test|xit|xtest|fit)'
            r'(?:\.(?!each\b)[a-zA-Z0-9_$]+)*'
            r'(?:\.each(?:\s*\((?:[^()]|\([^()]*\))*\)|\s*`[^`]*`))?'
            r'\s*\(\s*(?P<quote>[\'"`])(?P<name>.*?)(?P=quote)\s*,\s*'
            r'(?:'
            r'(?:async\s*)?(?:\([^)]*\)|[a-zA-Z0-9_$]+)\s*=>'
            r'|'
            r'(?:async\s+)?function(?:\s+[a-zA-Z0-9_$]+)?\s*\([^)]*\)'
            r')\s*\{',
            re.MULTILINE,
        )

        matches = list(test_block_pattern.finditer(self.content))
        self.scanned_tests = len(matches)

        for i, match in enumerate(matches):
            test_name = match.group("name")
            start_pos = match.start()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(self.content)
            block_code = self.content[start_pos:end_pos]
            start_line = self.content[:start_pos].count("\n") + 1
            end_line = start_line + block_code.count("\n")

            self._audit_block(test_name, block_code, start_line, end_line, boundary_modules)

        # 3. If no test blocks were found (e.g. file-level helper test), scan whole file
        if self.scanned_tests == 0 and ("expect(" in self.content or "assert(" in self.content):
            self.scanned_tests = 1
            self._audit_block("suite", self.content, 1, len(self.lines), boundary_modules)

        return self.smells, self.exemptions, self.scanned_tests

    def _audit_block(
        self,
        test_name: str,
        block_code: str,
        start_line: int,
        end_line: int,
        boundary_modules: List[str],
    ) -> None:
        block_lines = block_code.splitlines()

        # SM001: Zero-State Tautology
        mock_matchers = len(re.findall(r'\.(?:toHaveBeenCalled|toBeCalled)', block_code))
        state_matchers = len(
            re.findall(
                r'\.(?:toBe|toEqual|toStrictEqual|toMatch|toContain|toHaveLength|toHaveProperty|toBeDefined|toBeNull|toBeTruthy|toBeFalsy|toThrow|toBeGreaterThan|toBeLessThan)\s*\(',
                block_code,
            )
        )

        if mock_matchers >= 1 and state_matchers == 0:
            if not _is_rule_suppressed("SM001", start_line, start_line, end_line, self.pragmas):
                self.smells.append(
                    TestSmell(
                        file_path=self.file_path,
                        line_number=start_line,
                        rule_id=SmellType.ZERO_STATE_TAUTOLOGY.value,
                        severity=SmellSeverity.HARD_REJECTION.value,
                        message=(
                            f"Zero-State Tautology detected (It == 1.0): Test '{test_name}' asserts "
                            f"{mock_matchers} mock call(s) with 0 state/data assertions."
                        ),
                        context_snippet=_get_context_snippet(self.lines, start_line),
                        test_name=test_name,
                        remediation="Add assertions verifying returned values, mutated properties, or persistent data records.",
                        metrics={"mock_matchers": mock_matchers, "state_matchers": state_matchers, "it": 1.0},
                    )
                )

        # SM002: Direct Component Function Calls vs Mounting
        # Detect Header(props) or Button({ onClick }) instead of render(<Header />)
        # Exclude dot-preceded property calls like ApiClient.Connect(), Result.Ok(), DateTime.Now()
        pascal_call_pattern = re.compile(r'(?<!\.)(?<!\?)(?<!new\s)(?<!<\s)\b([A-Z][a-zA-Z0-9]+)\s*\(')
        for offset, bline in enumerate(block_lines):
            cur_line = start_line + offset
            # Skip lines with mounting or standard react creation
            if any(m in bline for m in ("render(", "mount(", "shallow(", "renderHook(", "createElement(", "jsx(", "jsxs(")):
                continue

            for p_match in pascal_call_pattern.finditer(bline):
                callee = p_match.group(1)
                callee_start = p_match.start(1)

                # Check preceding token context on the line:
                # Exclude static methods and chained calls preceded by '.' or '?.'
                prefix = bline[:callee_start].rstrip()
                if prefix.endswith(".") or prefix.endswith("?.") or prefix.endswith("new"):
                    continue

                if callee not in JS_BUILTIN_PASCAL_CASE:
                    # Ensure it's not a JSX tag on the same line
                    if f"<{callee}" in bline:
                        continue
                    if not _is_rule_suppressed("SM002", cur_line, start_line, end_line, self.pragmas):
                        self.smells.append(
                            TestSmell(
                                file_path=self.file_path,
                                line_number=cur_line,
                                rule_id=SmellType.DIRECT_COMPONENT_CALL.value,
                                severity=SmellSeverity.HARD_REJECTION.value,
                                message=(
                                    f"Direct component function call detected: Invoking '{callee}()' directly "
                                    f"instead of mounting via render() / mount()."
                                ),
                                context_snippet=_get_context_snippet(self.lines, cur_line),
                                test_name=test_name,
                                remediation="Mount the component using @testing-library/react ('render(<Component />)') or @vue/test-utils ('mount(Component)').",
                                metrics={"component": callee},
                            )
                        )

        # SM003: Fake Visual Regression Tests (Fake VRT)
        # expect(fs.existsSync('screenshot.png')).toBe(true)
        fake_vrt_pattern = re.compile(
            r'expect\s*\(\s*(?:fs\.)?existsSync\s*\((.*?)\)\s*\)\s*\.\s*(?:toBe\s*\(\s*true\s*\)|toBeTruthy\s*\(\s*\))'
        )
        # Require authentic VRT indicators to be invoked as a function or matcher call (e.g. difference(...) or .toHaveScreenshot())
        has_vrt_diff = any(
            re.search(r'(?:\b|\.)' + re.escape(ind) + r'\s*\(', block_code)
            for ind in VRT_DIFF_INDICATORS
        )
        for offset, bline in enumerate(block_lines):
            cur_line = start_line + offset
            match = fake_vrt_pattern.search(bline)
            if match and not has_vrt_diff:
                arg = match.group(1).lower()
                is_screenshot = any(ext in arg for ext in (".png", ".jpg", ".jpeg", ".webp", "screenshot", "snapshot"))
                if is_screenshot and not _is_rule_suppressed("SM003", cur_line, start_line, end_line, self.pragmas):
                    self.smells.append(
                        TestSmell(
                            file_path=self.file_path,
                            line_number=cur_line,
                            rule_id=SmellType.FAKE_VRT.value,
                            severity=SmellSeverity.HARD_REJECTION.value,
                            message=(
                                f"Fake Visual Regression Test detected: Test '{test_name}' asserts filesystem existence "
                                f"of screenshot without pixel/image comparison."
                            ),
                            context_snippet=_get_context_snippet(self.lines, cur_line),
                            test_name=test_name,
                            remediation="Replace filesystem existence check with real pixel buffer comparison (e.g. toHaveScreenshot).",
                        )
                    )

        # SM004: Echo Assertions
        # mockReturnValue({ id: 'x' }) followed by expect(res.id).toBe('x')
        EXCLUDED_TS_SCALARS = {"true", "false", "0", "1", "''", '""', '``', "", "null", "undefined"}
        mock_val_pattern = re.compile(
            r'\.(?:mockReturnValue|mockResolvedValue)(?:Once)?\s*\(\s*(\{.*?\}|\[.*?\]|[\'"`].*?[\'"`]|\b\d+\b|true|false)\s*\)',
            re.DOTALL,
        )
        mock_vals = mock_val_pattern.findall(block_code)
        if mock_vals:
            candidate_echo_values: List[str] = []
            for mv in mock_vals:
                mv_stripped = mv.strip()
                # Direct primitive match (excluding trivial scalars)
                cleaned_mv = mv_stripped.strip("'\"`")
                if cleaned_mv.lower() not in EXCLUDED_TS_SCALARS:
                    candidate_echo_values.append(cleaned_mv)
                    candidate_echo_values.append(mv_stripped)

                # Nested property / array element extraction
                if (mv_stripped.startswith("{") and mv_stripped.endswith("}")) or (
                    mv_stripped.startswith("[") and mv_stripped.endswith("]")
                ):
                    # Extract property values (: 'val' or : 123)
                    prop_values = re.findall(r'[:=]\s*([\'"`]?[^,\}\)\s\n]+[\'"`]?)', mv_stripped)
                    # Also extract array string elements
                    array_strings = re.findall(r'[\'"`]([^\'"`]+)[\'"`]', mv_stripped)
                    for pv in prop_values + array_strings:
                        cleaned_pv = pv.strip().strip("'\"`")
                        if cleaned_pv and cleaned_pv.lower() not in EXCLUDED_TS_SCALARS:
                            candidate_echo_values.append(cleaned_pv)
                            candidate_echo_values.append(pv.strip())

            for offset, bline in enumerate(block_lines):
                cur_line = start_line + offset
                # Skip mock definition line
                if "mockReturnValue" in bline or "mockResolvedValue" in bline:
                    continue
                for cev in candidate_echo_values:
                    if not cev or cev in {":", "{", "}"}:
                        continue
                    if f".toBe({cev})" in bline or f".toEqual({cev})" in bline or f".toStrictEqual({cev})" in bline:
                        if not _is_rule_suppressed("SM004", cur_line, start_line, end_line, self.pragmas):
                            self.smells.append(
                                TestSmell(
                                    file_path=self.file_path,
                                    line_number=cur_line,
                                    rule_id=SmellType.ECHO_ASSERTION.value,
                                    severity=SmellSeverity.WARNING.value,
                                    message=(
                                        f"Echo Assertion detected: Assertion in '{test_name}' strictly mirrors "
                                        f"hardcoded mock return value '{cev}'."
                                    ),
                                    context_snippet=_get_context_snippet(self.lines, cur_line),
                                    test_name=test_name,
                                    remediation="Verify downstream business transformation, state mutation, or edge cases rather than mirroring mock inputs.",
                                )
                            )
                            break

        # SM005: Boundary Exemption for TS/JS per test block
        block_boundary_modules = []
        for mod in BOUNDARY_MODULES:
            if (
                f"'{mod}'" in block_code
                or f'"{mod}"' in block_code
                or f"`{mod}`" in block_code
                or re.search(r'\b' + re.escape(mod) + r'\b', block_code)
            ):
                block_boundary_modules.append(mod)

        if block_boundary_modules and mock_matchers >= 3:
            self.exemptions.append(
                BoundaryExemptionRecord(
                    file_path=self.file_path,
                    test_name=test_name,
                    reason=f"Waived mock density: wraps system boundary adapters ({', '.join(block_boundary_modules)})",
                    adapter_modules=block_boundary_modules,
                )
            )
        elif mock_matchers >= 3 and mock_matchers / max(1, mock_matchers + state_matchers) > 0.5:
            if not _is_rule_suppressed("SM005", start_line, start_line, end_line, self.pragmas):
                self.smells.append(
                    TestSmell(
                        file_path=self.file_path,
                        line_number=start_line,
                        rule_id=SmellType.MOCK_DENSITY_WARNING.value,
                        severity=SmellSeverity.WARNING.value,
                        message=(
                            f"High Mock Density detected: Test '{test_name}' relies heavily "
                            f"on mocks ({mock_matchers} mock matchers)."
                        ),
                        context_snippet=_get_context_snippet(self.lines, start_line),
                        test_name=test_name,
                        remediation="Reduce mock coupling by testing through public interfaces or stateful integration tests.",
                        metrics={"mock_operations": mock_matchers, "mock_density": mock_matchers / max(1, mock_matchers + state_matchers)},
                    )
                )


def audit_file_smells(file_path: Union[str, Path], content: Optional[str] = None) -> List[TestSmell]:
    """
    Audits a single test file for synthetic test smells.
    Returns list of TestSmell violations.
    """
    path_obj = Path(file_path).resolve()
    if content is None:
        try:
            content = path_obj.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

    lines = content.splitlines()
    pragmas = _extract_pragmas(lines)
    ext = path_obj.suffix.lower()

    if ext == ".py":
        try:
            tree = ast.parse(content, filename=str(path_obj))
        except SyntaxError:
            return []
        visitor = PythonTestSmellVisitor(str(path_obj), lines, pragmas)
        visitor.visit(tree)
        return visitor.smells

    elif ext in {".ts", ".tsx", ".js", ".jsx"}:
        scanner = TSJSTestSmellScanner(str(path_obj), content)
        smells, _, _ = scanner.scan()
        return smells

    return []


def audit_workspace_test_smells(
    target_path: Optional[Union[str, Path]] = None,
    workspace_root: Optional[Union[str, Path]] = None,
) -> SmellAuditReport:
    """
    Scans a workspace or target directory for synthetic test smells across all test suites.
    """
    root_dir = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
    report = SmellAuditReport(
        workspace_root=str(root_dir),
        target_path=str(target_path) if target_path else None,
        scanned_files=0,
        scanned_tests=0,
    )

    # 1. Determine files to scan
    target_files: List[Path] = []
    if target_path:
        tp = Path(target_path)
        if not tp.is_absolute():
            tp = (root_dir / tp).resolve()
        if not tp.exists():
            report.passed = False
            sys.stderr.write(f"Error: Target test path does not exist: {target_path}\n")
            return report
        if tp.is_file():
            target_files = [tp]
        elif tp.is_dir():
            target_files = _find_test_files_in_dir(tp)
    else:
        # Default: scan tests/ directory if present, else scan repository test files
        tests_dir = root_dir / "tests"
        if tests_dir.is_dir():
            target_files = _find_test_files_in_dir(tests_dir)
        else:
            target_files = _find_test_files_in_dir(root_dir)

    # 2. Audit each test file
    for tf in target_files:
        try:
            content = tf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        report.scanned_files += 1
        lines = content.splitlines()
        pragmas = _extract_pragmas(lines)
        ext = tf.suffix.lower()

        if ext == ".py":
            try:
                tree = ast.parse(content, filename=str(tf))
                visitor = PythonTestSmellVisitor(str(tf), lines, pragmas)
                visitor.visit(tree)
                report.scanned_tests += visitor.scanned_tests
                for s in visitor.smells:
                    if s.severity == SmellSeverity.HARD_REJECTION.value:
                        report.hard_rejections.append(s)
                    else:
                        report.warnings.append(s)
                report.exemptions.extend(visitor.exemptions)
            except SyntaxError:
                continue

        elif ext in {".ts", ".tsx", ".js", ".jsx"}:
            scanner = TSJSTestSmellScanner(str(tf), content)
            smells, exemptions, tests_count = scanner.scan()
            report.scanned_tests += tests_count
            for s in smells:
                if s.severity == SmellSeverity.HARD_REJECTION.value:
                    report.hard_rejections.append(s)
                else:
                    report.warnings.append(s)
            report.exemptions.extend(exemptions)

    report.passed = len(report.hard_rejections) == 0
    return report


ADAPTER_PATTERNS_A = re.compile(r"(?:Adapter|Socket|Docker|Client|Process)", re.IGNORECASE)
ADAPTER_DECORATORS_A = {"mock_network", "adapter_boundary"}
NON_COMPONENT_PASCAL_A = {
    "Array", "Boolean", "Buffer", "Date", "Error", "Map", "Number", "Object",
    "Promise", "RegExp", "Set", "String", "Symbol", "URL", "Path", "Mock",
    "MagicMock", "TestCase", "Exception", "ValueError", "TypeError", "RuntimeError",
    "KeyError", "IndexError", "AttributeError", "StopIteration", "BytesIO", "StringIO",
    "Function", "BigInt", "RangeError", "SyntaxError", "ReferenceError", "URIError",
    "EvalError", "WeakMap", "WeakSet", "ArrayBuffer", "SharedArrayBuffer", "DataView",
    "Int8Array", "Uint8Array", "Uint8ClampedArray", "Int16Array", "Uint16Array",
    "Int32Array", "Uint32Array", "Float32Array", "Float64Array", "BigInt64Array",
    "BigUint64Array", "URLSearchParams", "JSON", "Math", "Reflect", "Proxy", "Intl",
    "File", "Blob", "FormData", "Headers", "Request", "Response", "AbortController",
    "Event", "CustomEvent", "EventTarget", "Describe", "Test", "It", "Expect",
    "BeforeEach", "AfterEach", "BeforeAll", "AfterAll", "Suite",
}
VRT_KEYWORDS_A = {"screenshot", "snapshot", ".png", ".jpg", ".jpeg", "screenshotpath", "screenshot_path"}
VISUAL_DIFF_KEYWORDS_A = {
    "pixelmatch", "looks-same", "lookssame", "tomatchimagesnapshot", "assert_images_equal",
    "compare_images", "image_diff", "diff_images", "perceptual_diff"
}


def _is_adapter_boundary_a(path: Path, class_name: Optional[str] = None, decorators: Optional[List[str]] = None) -> bool:
    if ADAPTER_PATTERNS_A.search(path.stem):
        return True
    if class_name and ADAPTER_PATTERNS_A.search(class_name):
        return True
    if decorators:
        for dec in decorators:
            dec_clean = dec.split(".")[-1].lower()
            if dec_clean in ADAPTER_DECORATORS_A:
                return True
    return False


def _get_decorator_names_a(decorator_list: List[ast.AST]) -> List[str]:
    names: List[str] = []
    for d in decorator_list:
        if isinstance(d, ast.Name):
            names.append(d.id)
        elif isinstance(d, ast.Attribute):
            names.append(f"{ast.unparse(d)}")
        elif isinstance(d, ast.Call):
            if isinstance(d.func, (ast.Name, ast.Attribute)):
                names.append(ast.unparse(d.func))
    return names


class RouteAPythonTestSmellVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path, source_lines: List[str]):
        self.file_path = file_path
        self.source_lines = source_lines
        self.issues: List[TestSmell] = []
        self.current_class: Optional[str] = None
        self.class_decorators: List[str] = []
        self.current_function: str = ""
        self.is_file_adapter = _is_adapter_boundary_a(file_path)

    def _get_line_snippet(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1]
        return ""

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        old_class = self.current_class
        old_decs = self.class_decorators
        self.current_class = node.name
        self.class_decorators = _get_decorator_names_a(node.decorator_list)
        self.generic_visit(node)
        self.current_class = old_class
        self.class_decorators = old_decs

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._analyze_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._analyze_function(node)

    def _analyze_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        old_fn = self.current_function
        self.current_function = node.name
        fn_decorators = _get_decorator_names_a(node.decorator_list)
        is_adapter = (
            self.is_file_adapter
            or _is_adapter_boundary_a(self.file_path, self.current_class, self.class_decorators + fn_decorators)
        )
        is_test_fn = node.name.startswith("test_") or node.name.endswith("_test")

        mock_assertion_calls: List[Tuple[ast.Call, int]] = []
        state_assertions: List[Tuple[ast.AST, int]] = []
        mock_return_values: Dict[str, Any] = {}
        assigned_constants: Dict[str, Any] = {}
        has_visual_diff = False

        fn_text = ast.unparse(node).lower()
        for vdk in VISUAL_DIFF_KEYWORDS_A:
            if vdk in fn_text:
                has_visual_diff = True
                break

        for stmt in node.body:
            self._scan_statement(
                stmt=stmt,
                mock_assertion_calls=mock_assertion_calls,
                state_assertions=state_assertions,
                mock_return_values=mock_return_values,
                assigned_constants=assigned_constants,
                has_visual_diff=has_visual_diff,
            )

        if is_test_fn and not is_adapter:
            if mock_assertion_calls and not state_assertions:
                first_call, lineno = mock_assertion_calls[0]
                self.issues.append(
                    TestSmell(
                        file_path=str(self.file_path),
                        line_number=lineno,
                        rule_id=RuleIdStr("zero-state-tautology"),
                        severity=SeverityStr("ERROR"),
                        message=(
                            "Mock-only tautology: test function contains only mock call assertions "
                            "with zero state, return value, or output assertions."
                        ),
                        context_snippet=self._get_line_snippet(lineno),
                        test_name=self.current_function,
                    )
                )

        self.generic_visit(node)
        self.current_function = old_fn

    def _scan_statement(
        self,
        stmt: ast.AST,
        mock_assertion_calls: List[Tuple[ast.Call, int]],
        state_assertions: List[Tuple[ast.AST, int]],
        mock_return_values: Dict[str, Any],
        assigned_constants: Dict[str, Any],
        has_visual_diff: bool,
    ) -> None:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Attribute) and target.attr == "return_value":
                    val_repr = ast.unparse(stmt.value)
                    mock_repr = ast.unparse(target.value)
                    mock_return_values[mock_repr] = val_repr
                elif isinstance(target, ast.Name):
                    if isinstance(stmt.value, ast.Constant):
                        assigned_constants[target.id] = stmt.value.value
                    elif isinstance(stmt.value, ast.Call):
                        call_repr = ast.unparse(stmt.value.func)
                        if call_repr in mock_return_values:
                            mock_return_values[target.id] = mock_return_values[call_repr]

        for subnode in ast.walk(stmt):
            if isinstance(subnode, ast.Assert):
                self._check_assert_node(
                    subnode, state_assertions, mock_return_values, assigned_constants, has_visual_diff
                )
            elif isinstance(subnode, ast.Call):
                self._check_call_node(
                    subnode, mock_assertion_calls, state_assertions, mock_return_values, assigned_constants, has_visual_diff
                )

    def _check_assert_node(
        self,
        node: ast.Assert,
        state_assertions: List[Tuple[ast.AST, int]],
        mock_return_values: Dict[str, Any],
        assigned_constants: Dict[str, Any],
        has_visual_diff: bool,
    ) -> None:
        test = node.test
        lineno = getattr(node, "lineno", 1)

        # Skip assert False, "unreachable"
        if isinstance(test, ast.Constant) and test.value is False:
            return

        if isinstance(test, ast.Constant) and bool(test.value):
            self.issues.append(
                TestSmell(
                    file_path=str(self.file_path),
                    line_number=lineno,
                    rule_id=RuleIdStr("zero-state-tautology"),
                    severity=SeverityStr("ERROR"),
                    message=f"Zero-state tautology: constant assertion 'assert {test.value}'",
                    context_snippet=self._get_line_snippet(lineno),
                    test_name=self.current_function,
                )
            )
            return

        if isinstance(test, ast.Compare):
            left = test.left
            for op, right in zip(test.ops, test.comparators):
                left_dump = ast.dump(left)
                right_dump = ast.dump(right)
                left_unparsed = ast.unparse(left)
                right_unparsed = ast.unparse(right)

                if left_dump == right_dump and isinstance(op, (ast.Eq, ast.Is, ast.LtE, ast.GtE)):
                    self.issues.append(
                        TestSmell(
                            file_path=str(self.file_path),
                            line_number=lineno,
                            rule_id=RuleIdStr("zero-state-tautology"),
                            severity=SeverityStr("ERROR"),
                            message=f"Zero-state tautology: identical operand comparison 'assert {left_unparsed} == {right_unparsed}'",
                            context_snippet=self._get_line_snippet(lineno),
                            test_name=self.current_function,
                        )
                    )
                    return

                if isinstance(left, ast.Constant) and isinstance(right, ast.Constant):
                    self.issues.append(
                        TestSmell(
                            file_path=str(self.file_path),
                            line_number=lineno,
                            rule_id=RuleIdStr("zero-state-tautology"),
                            severity=SeverityStr("ERROR"),
                            message=f"Zero-state tautology: constant literal comparison 'assert {left_unparsed} == {right_unparsed}'",
                            context_snippet=self._get_line_snippet(lineno),
                            test_name=self.current_function,
                        )
                    )
                    return

                for mock_name, ret_val in mock_return_values.items():
                    if (left_unparsed == mock_name and right_unparsed == ret_val) or (
                        right_unparsed == mock_name and left_unparsed == ret_val
                    ):
                        self.issues.append(
                            TestSmell(
                                file_path=str(self.file_path),
                                line_number=lineno,
                                rule_id=RuleIdStr("echo-assertion"),
                                severity=SeverityStr("WARNING"),
                                message=(
                                    f"Echo assertion: mock return value '{ret_val}' mirrored directly "
                                    f"into assertion target '{mock_name}' without business logic transformation."
                                ),
                                context_snippet=self._get_line_snippet(lineno),
                                test_name=self.current_function,
                            )
                        )

        test_unparsed = ast.unparse(test)
        if any(v in test_unparsed.lower() for v in VRT_KEYWORDS_A):
            if ("exists(" in test_unparsed or ".exists()" in test_unparsed) and not has_visual_diff:
                self.issues.append(
                    TestSmell(
                        file_path=str(self.file_path),
                        line_number=lineno,
                        rule_id=RuleIdStr("fake-vrt"),
                        severity=SeverityStr("ERROR"),
                        message="Fake VRT: asserting file existence on screenshot/snapshot instead of perceptual or pixel visual comparison.",
                        context_snippet=self._get_line_snippet(lineno),
                        test_name=self.current_function,
                    )
                )
                return

        state_assertions.append((node, lineno))

    def _check_call_node(
        self,
        node: ast.Call,
        mock_assertion_calls: List[Tuple[ast.Call, int]],
        state_assertions: List[Tuple[ast.AST, int]],
        mock_return_values: Dict[str, Any],
        assigned_constants: Dict[str, Any],
        has_visual_diff: bool,
    ) -> None:
        lineno = getattr(node, "lineno", 1)

        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if (
                func_name[0].isupper()
                and func_name not in NON_COMPONENT_PASCAL_A
                and not func_name.endswith("Error")
                and not func_name.endswith("Exception")
            ):
                if func_name.endswith("Component") or "Component(" in self._get_line_snippet(lineno):
                    self.issues.append(
                        TestSmell(
                            file_path=str(self.file_path),
                            line_number=lineno,
                            rule_id=RuleIdStr("direct-component-call"),
                            severity=SeverityStr("ERROR"),
                            message=f"Direct Component call '{func_name}(...)' in test without DOM mounting (e.g. render, mount, shallow).",
                            context_snippet=self._get_line_snippet(lineno),
                            test_name=self.current_function,
                        )
                    )

        if isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if attr in (
                "assert_called", "assert_called_once", "assert_called_with",
                "assert_called_once_with", "assert_any_call", "assert_has_calls",
                "assert_not_called",
            ):
                mock_assertion_calls.append((node, lineno))
                return

            if attr.startswith("assert"):
                self._check_unittest_assert(
                    attr=attr,
                    node=node,
                    lineno=lineno,
                    state_assertions=state_assertions,
                    mock_return_values=mock_return_values,
                    assigned_constants=assigned_constants,
                    has_visual_diff=has_visual_diff,
                )

    def _check_unittest_assert(
        self,
        attr: str,
        node: ast.Call,
        lineno: int,
        state_assertions: List[Tuple[ast.AST, int]],
        mock_return_values: Dict[str, Any],
        assigned_constants: Dict[str, Any],
        has_visual_diff: bool,
    ) -> None:
        if attr == "assertTrue" and node.args:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant) and bool(first_arg.value):
                self.issues.append(
                    TestSmell(
                        file_path=str(self.file_path),
                        line_number=lineno,
                        rule_id=RuleIdStr("zero-state-tautology"),
                        severity=SeverityStr("ERROR"),
                        message=f"Zero-state tautology: unittest 'self.assertTrue({first_arg.value})'",
                        context_snippet=self._get_line_snippet(lineno),
                        test_name=self.current_function,
                    )
                )
                return

        if attr in ("assertEqual", "assertIs") and len(node.args) >= 2:
            arg1, arg2 = node.args[0], node.args[1]
            arg1_dump, arg2_dump = ast.dump(arg1), ast.dump(arg2)
            arg1_unparsed, arg2_unparsed = ast.unparse(arg1), ast.unparse(arg2)

            if arg1_dump == arg2_dump:
                self.issues.append(
                    TestSmell(
                        file_path=str(self.file_path),
                        line_number=lineno,
                        rule_id=RuleIdStr("zero-state-tautology"),
                        severity=SeverityStr("ERROR"),
                        message=f"Zero-state tautology: identical operand unittest 'self.{attr}({arg1_unparsed}, {arg2_unparsed})'",
                        context_snippet=self._get_line_snippet(lineno),
                        test_name=self.current_function,
                    )
                )
                return

            if isinstance(arg1, ast.Constant) and isinstance(arg2, ast.Constant):
                self.issues.append(
                    TestSmell(
                        file_path=str(self.file_path),
                        line_number=lineno,
                        rule_id=RuleIdStr("zero-state-tautology"),
                        severity=SeverityStr("ERROR"),
                        message=f"Zero-state tautology: constant comparison 'self.{attr}({arg1_unparsed}, {arg2_unparsed})'",
                        context_snippet=self._get_line_snippet(lineno),
                        test_name=self.current_function,
                    )
                )
                return

            for mock_name, ret_val in mock_return_values.items():
                if (arg1_unparsed == mock_name and arg2_unparsed == ret_val) or (
                    arg2_unparsed == mock_name and arg1_unparsed == ret_val
                ):
                    self.issues.append(
                        TestSmell(
                            file_path=str(self.file_path),
                            line_number=lineno,
                            rule_id=RuleIdStr("echo-assertion"),
                            severity=SeverityStr("WARNING"),
                            message=f"Echo assertion: mock return value '{ret_val}' mirrored directly into assertion target '{mock_name}' without business logic transformation.",
                            context_snippet=self._get_line_snippet(lineno),
                            test_name=self.current_function,
                        )
                    )

        if attr == "assertAlmostEqual" and len(node.args) >= 2:
            arg1, arg2 = node.args[0], node.args[1]
            if isinstance(arg1, ast.Constant) and isinstance(arg2, ast.Constant):
                self.issues.append(
                    TestSmell(
                        file_path=str(self.file_path),
                        line_number=lineno,
                        rule_id=RuleIdStr("zero-state-tautology"),
                        severity=SeverityStr("ERROR"),
                        message="Zero-state tautology: assertAlmostEqual with constant literals",
                        context_snippet=self._get_line_snippet(lineno),
                        test_name=self.current_function,
                    )
                )
                return

            if isinstance(arg1, ast.Name) and isinstance(arg2, ast.Constant):
                if arg1.id in assigned_constants and assigned_constants[arg1.id] == arg2.value:
                    self.issues.append(
                        TestSmell(
                            file_path=str(self.file_path),
                            line_number=lineno,
                            rule_id=RuleIdStr("zero-state-tautology"),
                            severity=SeverityStr("ERROR"),
                            message=f"Zero-state tautology: assertAlmostEqual({arg1.id}, {arg2.value}) where variable is unmodified constant",
                            context_snippet=self._get_line_snippet(lineno),
                            test_name=self.current_function,
                        )
                    )
                    return

        call_unparsed = ast.unparse(node)
        if any(v in call_unparsed.lower() for v in VRT_KEYWORDS_A):
            if ("exists(" in call_unparsed or ".exists()" in call_unparsed) and not has_visual_diff:
                self.issues.append(
                    TestSmell(
                        file_path=str(self.file_path),
                        line_number=lineno,
                        rule_id=RuleIdStr("fake-vrt"),
                        severity=SeverityStr("ERROR"),
                        message="Fake VRT: asserting file existence on screenshot/snapshot instead of perceptual or pixel visual comparison.",
                        context_snippet=self._get_line_snippet(lineno),
                        test_name=self.current_function,
                    )
                )
                return

        state_assertions.append((node, lineno))


def audit_test_file(path: Union[str, Path], content: Optional[str] = None) -> List[TestSmell]:
    """Audits a single test file for synthetic test smells (Route A compatibility)."""
    return audit_file_smells(path, content=content)


def audit_test_smells(
    target_dir: Union[str, Path],
    files: Optional[List[Path]] = None,
) -> SmellAuditReport:
    """
    Audits test files under target_dir or explicitly provided files (Route A compatibility).
    Returns SmellAuditReport (compatible with TestSmellReport).
    """
    target_dir = Path(target_dir).resolve()
    report = SmellAuditReport(
        workspace_root=str(target_dir),
        target_path=str(target_dir),
        scanned_files=0,
        scanned_tests=0,
    )
    if files is None:
        files = _find_test_files_in_dir(target_dir)

    for f in files:
        fp = Path(f).resolve()
        if fp.is_file():
            smells = audit_test_file(fp)
            report.scanned_files += 1
            report.scanned_tests += 1
            for s in smells:
                if s.severity in (SmellSeverity.HARD_REJECTION.value, "ERROR", "hard_rejection"):
                    report.hard_rejections.append(s)
                elif s.severity in (SmellSeverity.WARNING.value, "WARNING", "warning"):
                    report.warnings.append(s)
                elif s.severity in (SmellSeverity.EXEMPTION.value, "EXEMPTION"):
                    report.exemptions.append(s)
    report.passed = len(report.hard_rejections) == 0
    return report


def _find_test_files_in_dir(directory: Path) -> List[Path]:
    """Finds test files while skipping vendor/build artifacts."""
    excluded_dirs = {".git", "node_modules", ".agents", ".venv", "__pycache__", ".tox", "dist", "build"}
    test_files: List[Path] = []

    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in excluded_dirs]
        for f in files:
            p = Path(root) / f
            ext = p.suffix.lower()
            name = p.name.lower()
            if ext == ".py":
                if name.startswith("test_") or name.endswith("_test.py"):
                    test_files.append(p)
            elif ext in {".ts", ".tsx", ".js", ".jsx"}:
                if ".test." in name or ".spec." in name or name.startswith("test_"):
                    test_files.append(p)

    return sorted(test_files)


def print_ansi_smell_report(report: SmellAuditReport) -> None:
    """Formats and prints the smell audit report to stdout."""
    if report.target_path:
        tp = Path(report.target_path)
        if not tp.is_absolute():
            tp = Path(report.workspace_root) / tp
        if not tp.exists():
            print(f"❌ Error: Target test path does not exist: {report.target_path}")
            print("━" * 76)
            print("Summary: 0 files scanned | Target path not found")
            print("Result: FAILED (Exit Code 1)")
            return

    print("🩺 AGYIS WORKSTATION DOCTOR — ANTI-SYNTHETIC TEST SMELL AUDIT")
    print("━" * 76)
    target_display = report.target_path or (report.workspace_root + "/tests")
    print(f"Target: {target_display}")
    print(f"Scanned Files: {report.scanned_files} test files | Analyzed Tests: {report.scanned_tests} test cases")
    print()

    if report.hard_rejections:
        print(f"❌ HARD REJECTIONS ({len(report.hard_rejections)}):")
        for hr in report.hard_rejections:
            rel_file = hr.file_path
            try:
                rel_file = str(Path(hr.file_path).relative_to(report.workspace_root))
            except Exception:
                pass
            print(f"  [HARD REJECT] [{hr.rule_id}] {rel_file}:{hr.line_number} in {hr.test_name or 'test'} (zero-state-tautology)")
            print(f"    Message: {hr.message}")
            if hr.remediation:
                print(f"    Remediation: {hr.remediation}")
            if hr.context_snippet:
                snippet_indented = "\n".join("      " + l for l in hr.context_snippet.splitlines())
                print(f"    Context:\n{snippet_indented}")
            print()

    if report.warnings:
        print(f"⚠️  ACTIONABLE WARNINGS ({len(report.warnings)}):")
        for w in report.warnings:
            rel_file = w.file_path
            try:
                rel_file = str(Path(w.file_path).relative_to(report.workspace_root))
            except Exception:
                pass
            print(f"  [{w.rule_id}] {rel_file}:{w.line_number} in {w.test_name or 'test'}")
            print(f"    Message: {w.message}")
            if w.remediation:
                print(f"    Remediation: {w.remediation}")
            print()

    if report.exemptions:
        print(f"🛡️  BOUNDARY EXEMPTIONS ({len(report.exemptions)}):")
        for ex in report.exemptions:
            rel_file = ex.file_path
            try:
                rel_file = str(Path(ex.file_path).relative_to(report.workspace_root))
            except Exception:
                pass
            adapters_str = ", ".join(ex.adapter_modules) if ex.adapter_modules else "system boundary"
            print(f"  [BOUNDARY_EXEMPT] {rel_file} ({ex.test_name})")
            print(f"    Exemption: {ex.reason} [{adapters_str}]")
        print()

    print("━" * 76)
    status_str = "PASSED" if report.passed else "FAILED"
    print(
        f"Summary: {report.scanned_files} files scanned | "
        f"{len(report.hard_rejections)} Hard Rejections | "
        f"{len(report.warnings)} Warnings | "
        f"{len(report.exemptions)} Exemptions"
    )
    print(f"Result: {status_str} (Exit Code {'0' if report.passed else '1'})")


def run_anti_synthetic_doctor(
    target_path: Optional[Union[str, Path]] = None,
    format_json: bool = False,
    as_json: bool = False,
) -> int:
    """
    CLI entry point for 'agyis doctor --anti-synthetic'.
    Returns 0 if passed (no hard rejections), 1 if failed.
    """
    is_json = format_json or as_json
    report = audit_workspace_test_smells(target_path=target_path)

    if is_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_ansi_smell_report(report)

    return 0 if report.passed else 1
