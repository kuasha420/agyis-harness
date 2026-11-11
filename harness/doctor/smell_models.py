# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Shared constants, data models, pragmas, and ANSI reporting for test smell auditing."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

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
ADAPTER_DECORATORS: Set[str] = {"mock_network", "adapter_boundary"}

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
    "Array", "Object", "Function", "Boolean", "Number", "String", "Symbol", "BigInt",
    "Error", "TypeError", "RangeError", "SyntaxError", "ReferenceError", "URIError", "EvalError",
    "RegExp", "Date", "Promise", "Map", "Set", "WeakMap", "WeakSet", "ArrayBuffer",
    "SharedArrayBuffer", "DataView", "Int8Array", "Uint8Array", "Uint8ClampedArray",
    "Int16Array", "Uint16Array", "Int32Array", "Uint32Array", "Float32Array", "Float64Array",
    "BigInt64Array", "BigUint64Array", "URL", "URLSearchParams", "JSON", "Math", "Reflect",
    "Proxy", "Intl", "Buffer", "Path", "File", "Blob", "FormData", "Headers", "Request",
    "Response", "AbortController", "Event", "CustomEvent", "EventTarget", "Describe",
    "Test", "It", "Expect", "BeforeEach", "AfterEach", "BeforeAll", "AfterAll", "Suite",
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
                pragmas[idx] = {"*"}
            elif STRICT_RULE_ID_PATTERN.match(first_token):
                pragmas[idx] = {first_token.upper()}
            elif MALFORMED_RULE_PATTERN.match(first_token):
                pass
            else:
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
    if line_number in pragmas:
        rules = pragmas[line_number]
        if "*" in rules or rule_id in rules:
            return True

    for pre_line in (func_start - 1, func_start):
        if pre_line in pragmas:
            rules = pragmas[pre_line]
            if "*" in rules or rule_id in rules:
                return True

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


def _is_mock_call_inspection(node: ast.AST) -> bool:
    """Determine if an expression inspects mock call properties or invocations."""
    if isinstance(node, ast.Attribute):
        if node.attr in PYTHON_MOCK_PROP_ATTRS:
            return True
        return _is_mock_call_inspection(node.value)
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "len" and node.args:
            return _is_mock_call_inspection(node.args[0])
        if isinstance(node.func, ast.Attribute) and node.func.attr in PYTHON_MOCK_ASSERT_ATTRS:
            return True
        return False
    if isinstance(node, ast.Subscript):
        return _is_mock_call_inspection(node.value)
    if isinstance(node, ast.UnaryOp):
        return _is_mock_call_inspection(node.operand)
    if isinstance(node, ast.Compare):
        return _is_mock_call_inspection(node.left) or any(
            _is_mock_call_inspection(comp) for comp in node.comparators
        )
    return False


def _is_literal_constant(node: ast.AST) -> bool:
    """Determine if an AST node is a literal constant or container of constants."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_literal_constant(elt) for elt in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            (k is not None and _is_literal_constant(k)) and _is_literal_constant(v)
            for k, v in zip(node.keys, node.values)
        )
    if isinstance(node, ast.UnaryOp):
        return _is_literal_constant(node.operand)
    return False


def _is_trivial_expression(node: ast.AST) -> bool:
    """Determine if an assert expression is a trivial constant or identical comparison."""
    if _is_literal_constant(node):
        return True
    if isinstance(node, ast.Compare):
        if _is_literal_constant(node.left) and all(
            _is_literal_constant(comp) for comp in node.comparators
        ):
            return True
        return any(
            isinstance(op, (ast.Eq, ast.Is, ast.LtE, ast.GtE)) and ast.dump(node.left) == ast.dump(comp)
            for op, comp in zip(node.ops, node.comparators)
        )
    if isinstance(node, ast.BoolOp):
        return all(_is_trivial_expression(v) for v in node.values)
    if isinstance(node, ast.UnaryOp):
        return _is_trivial_expression(node.operand)
    return False


def _is_trivial_call_assertion(attr_name: str, args: List[ast.AST]) -> bool:
    """Determine if a unittest assert call asserts strictly on literal constants."""
    if not args:
        return True
    if attr_name in {"assertTrue", "assertFalse", "assertIsNone", "assertIsNotNone"}:
        return _is_trivial_expression(args[0])
    if attr_name in {"assertIsInstance", "assertNotIsInstance"}:
        return _is_literal_constant(args[0])
    if len(args) >= 2:
        return _is_trivial_expression(args[0]) and _is_trivial_expression(args[1])
    return False


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
            rule_alias = RuleIdStr._MAP.get(str(hr.rule_id).lower(), str(hr.rule_id))
            print(f"  [HARD REJECT] [{hr.rule_id}] {rel_file}:{hr.line_number} in {hr.test_name or 'test'} ({rule_alias})")
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
