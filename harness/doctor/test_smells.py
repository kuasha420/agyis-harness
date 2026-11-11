# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Anti-Synthetic Test Linting & Mutation Testing Gate (Epic #51 / Phase 3.1).
Detects synthetic unit tests across Python (AST) and TypeScript/JavaScript (Lexical/Pattern) suites:
- SM001: Zero-State Tautologies (asserts mock calls with 0 state/data assertions; It == 1.0)
- SM002: Direct Component Function Calls vs Mounting (Component(props) vs render(<Component />))
- SM003: Fake Visual Regression Tests (fs.existsSync(screenshot) without pixel buffer diffing)
- SM004: Echo Assertions (assertions echoing hardcoded mock return values without logic transform)
- SM005: High Mock Density Warning (with automatic Boundary Exemption for socket/subprocess/Docker)
- Escape Pragma: `# agyis: no-smell <RULE_ID> [--reason "..."]` or `// agyis: no-smell ...`
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import re
import sys
from typing import List, Optional, Tuple, Union

from harness.doctor.python_smell_visitor import PythonTestSmellVisitor
from harness.doctor.smell_models import (
    ADAPTER_DECORATORS,
    ADAPTER_PATTERNS,
    BOUNDARY_MODULES,
    BOUNDARY_PATH_KEYWORDS,
    BoundaryExemptionRecord,
    EXCLUDED_ECHO_SCALARS,
    JS_BUILTIN_PASCAL_CASE,
    MALFORMED_RULE_PATTERN,
    PRAGMA_PATTERN,
    PYTHON_MOCK_ASSERT_ATTRS,
    PYTHON_MOCK_PROP_ATTRS,
    PYTHON_STATE_ASSERT_ATTRS,
    RuleIdStr,
    STRICT_RULE_ID_PATTERN,
    SeverityStr,
    SmellAuditReport,
    SmellSeverity,
    SmellType,
    TestSmell,
    TestSmellIssue,
    TestSmellReport,
    VRT_DIFF_INDICATORS,
    _extract_nested_leaf_values,
    _extract_pragmas,
    _get_context_snippet,
    _is_excluded_echo_scalar,
    _is_literal_constant,
    _is_mock_call_inspection,
    _is_rule_suppressed,
    _is_trivial_call_assertion,
    _is_trivial_expression,
    print_ansi_smell_report,
)

__all__ = [
    "ADAPTER_DECORATORS",
    "ADAPTER_PATTERNS",
    "BOUNDARY_MODULES",
    "BOUNDARY_PATH_KEYWORDS",
    "BoundaryExemptionRecord",
    "EXCLUDED_ECHO_SCALARS",
    "JS_BUILTIN_PASCAL_CASE",
    "MALFORMED_RULE_PATTERN",
    "PRAGMA_PATTERN",
    "PYTHON_MOCK_ASSERT_ATTRS",
    "PYTHON_MOCK_PROP_ATTRS",
    "PYTHON_STATE_ASSERT_ATTRS",
    "PythonTestSmellVisitor",
    "RuleIdStr",
    "STRICT_RULE_ID_PATTERN",
    "SeverityStr",
    "SmellAuditReport",
    "SmellSeverity",
    "SmellType",
    "TSJSTestSmellScanner",
    "TestSmell",
    "TestSmellIssue",
    "TestSmellReport",
    "VRT_DIFF_INDICATORS",
    "_extract_nested_leaf_values",
    "_extract_pragmas",
    "_find_test_files_in_dir",
    "_get_context_snippet",
    "_is_excluded_echo_scalar",
    "_is_literal_constant",
    "_is_mock_call_inspection",
    "_is_rule_suppressed",
    "_is_trivial_call_assertion",
    "_is_trivial_expression",
    "audit_file_smells",
    "audit_test_file",
    "audit_test_smells",
    "audit_workspace_test_smells",
    "print_ansi_smell_report",
    "run_anti_synthetic_doctor",
]


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
        except (OSError, UnicodeDecodeError):
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


def _audit_target_file_into_report(tf: Path, report: SmellAuditReport) -> None:
    """Scans a single test file and records tests, smells, and exemptions into report."""
    try:
        content = tf.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return

    report.scanned_files += 1
    lines = content.splitlines()
    pragmas = _extract_pragmas(lines)
    ext = tf.suffix.lower()

    if ext == ".py":
        try:
            tree = ast.parse(content, filename=str(tf))
        except SyntaxError:
            return
        visitor = PythonTestSmellVisitor(str(tf), lines, pragmas)
        visitor.visit(tree)
        report.scanned_tests += visitor.scanned_tests
        for s in visitor.smells:
            (report.hard_rejections if s.severity == SmellSeverity.HARD_REJECTION.value else report.warnings).append(s)
        report.exemptions.extend(visitor.exemptions)
    elif ext in {".ts", ".tsx", ".js", ".jsx"}:
        scanner = TSJSTestSmellScanner(str(tf), content)
        smells, exemptions, tests_count = scanner.scan()
        report.scanned_tests += tests_count
        for s in smells:
            (report.hard_rejections if s.severity == SmellSeverity.HARD_REJECTION.value else report.warnings).append(s)
        report.exemptions.extend(exemptions)


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
        _audit_target_file_into_report(tf, report)

    report.passed = len(report.hard_rejections) == 0
    return report


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
            _audit_target_file_into_report(fp, report)
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
