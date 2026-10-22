# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Diff-Aware In-Harness Micro-Mutator Engine (ADR-014, ADR-015, Epic #51 Phase 3.1).

Architectural Invariants Enforced:
1. Diff-Targeted: Only mutate uncommitted working tree lines in git diff HEAD.
2. Arid-Line Suppression: Skip imports, type annotations, comments, docstrings, logs.
3. 5-6 Mutation Operators: Condition invert, logic swap, boundary shift, return stub, void delete.
4. Diversity Sampling: Cap at 5-6 mutants per modified function.
5. Affected Test Execution: Strictly execute Tier 1A affected tests via harness.discovery.
6. Actionable Feedback: Emit clear unified diff snippets and surviving mutant locations.
7. Inline Pragma: Support '# agyis: no-mutant <reason>' for verified equivalent mutants.
8. Crash Safety: Atomic in-memory backups, try...finally restoration, atexit, and signal traps.
"""

from __future__ import annotations

import ast
import atexit
import copy
from dataclasses import dataclass, field
import difflib
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

from harness.discovery import (
    inject_non_interactive_guards,
    resolve_affected_tests,
)

# Active file backups for crash safety: maps absolute Path -> original file text
ACTIVE_BACKUPS: Dict[Path, str] = {}
_SAFETY_HANDLERS_INSTALLED = False
_SAFETY_LOCK = threading.Lock()

MUTATABLE_EXTENSIONS: Set[str] = {".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go"}


def is_test_file(path_str: str) -> bool:
    """Checks whether a relative or absolute path represents a test file."""
    p = Path(path_str)
    if any(part in ("tests", "test", "__tests__") for part in p.parts):
        return True
    name = p.name
    if name.startswith("test_") or name.endswith(
        ("_test.py", ".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx", ".test.js", ".spec.js")
    ):
        return True
    return False


def _restore_all_backups() -> None:
    """Restores all active in-memory backups to disk on shutdown or interruption."""
    with _SAFETY_LOCK:
        for path, original_content in list(ACTIVE_BACKUPS.items()):
            try:
                if path.exists():
                    path.write_text(original_content, encoding="utf-8")
            except Exception:
                pass
        ACTIVE_BACKUPS.clear()


def _sig_handler(signum: int, frame: Any) -> None:
    """Signal trap for SIGINT and SIGTERM."""
    _restore_all_backups()
    sys.exit(128 + signum)


def _install_safety_handlers() -> None:
    """Installs atexit and signal traps for hermetic crash recovery."""
    global _SAFETY_HANDLERS_INSTALLED
    with _SAFETY_LOCK:
        if _SAFETY_HANDLERS_INSTALLED:
            return
        atexit.register(_restore_all_backups)
        try:
            if threading.current_thread() is threading.main_thread():
                signal.signal(signal.SIGINT, _sig_handler)
                signal.signal(signal.SIGTERM, _sig_handler)
        except (ValueError, AttributeError):
            pass
        _SAFETY_HANDLERS_INSTALLED = True


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class SurvivingMutant:
    """Represents a mutant that survived execution (tests passed despite mutation)."""
    file_path: str
    function_name: str
    line_number: int
    operator: str
    diff_snippet: str
    test_target: str

    def to_actionable_report(self) -> str:
        """Formats an actionable diagnostic diff and cognitive guidance report."""
        loc = f"{self.file_path}:{self.line_number}"
        return (
            f"\n❌ MUTATION TEST FAILURE: Surviving mutant detected!\n"
            f"The test suite passed on mutated code, indicating missing test assertions.\n\n"
            f"──────────────────────────────────────────────────────────────────────\n"
            f"[Surviving Mutant]\n"
            f"  Location: {loc}\n"
            f"  Function: `{self.function_name}`\n"
            f"  Operator: {self.operator}\n"
            f"  Test Target: {self.test_target}\n"
            f"──────────────────────────────────────────────────────────────────────\n"
            f"Unified Diff:\n"
            f"{self.diff_snippet}\n\n"
            f"Cognitive Guidance:\n"
            f"  • Your tests passed even when {self.operator} was applied to {loc}.\n"
            f"  • Remediation: Add test assertions exercising this branch or boundary.\n"
            f"  • Equivalent Mutant? If semantically equivalent, suppress with:\n"
            f"    # agyis: no-mutant <reason>\n"
            f"──────────────────────────────────────────────────────────────────────\n"
        )


@dataclass
class MutationResult:
    """Result of micro-mutation testing across the working tree or target diff."""
    total_mutants: int
    killed_mutants: int
    survived_mutants: List[SurvivingMutant] = field(default_factory=list)
    exit_code: int = 0
    suppressed_by_pragma: int = 0


@dataclass
class MutationConfig:
    """Configuration options for micro-mutation execution."""
    max_mutants_per_function: int = 6
    max_mutants_total: int = 20
    operators: Optional[List[str]] = None
    timeout_sec: float = 3.0
    fail_fast: bool = False
    repo_root: Optional[Path] = None
    verbose: bool = False


@dataclass
class MutationCandidate:
    """A target code line identified from a diff hunk."""
    file_path: str
    line_number: int
    content: str


@dataclass
class FunctionMutant:
    """A planned mutant for a function or code block."""
    mutated_code: str
    operator: str
    line_number: int
    diff_snippet: str
    function_name: str = ""


# ---------------------------------------------------------------------------
# Pragmas and Arid-Line Filter
# ---------------------------------------------------------------------------

PRAGMA_PATTERN = re.compile(r"(?:#|//)\s*(?:agyis:\s*no-mutant|no-mutant:)", re.IGNORECASE)
TYPE_ANNOTATION_ONLY = re.compile(r"^\s*[a-zA-Z_][a-zA-Z0-9_]*\s*:\s*[^=]+$")


def has_no_mutant_pragma(line: str) -> bool:
    """
    Checks whether a line contains the inline escape pragma '# agyis: no-mutant' or '# no-mutant:'.
    Matches arbitrary spacing, tabs, and unicode descriptions (case-insensitive).
    """
    return bool(PRAGMA_PATTERN.search(line))


def is_arid_line(line: str) -> bool:
    """
    Checks whether a line is non-logic arid code:
    - Imports: import os, from x import y, use std::..., require(...)
    - Type definitions: type X = ..., interface Y, typedef ...
    - Comments: # ..., // ..., /* ..., * ...
    - Docstrings: \"\"\"...\"\"\", '''...'''
    - Log/print statements: print(...), console.log(...), logger.info(...)
    - Empty or whitespace lines
    """
    s = line.strip()
    if not s:
        return True
    # Comments
    if s.startswith("#") or s.startswith("//") or s.startswith("/*") or s.startswith("*"):
        return True
    # Docstrings
    if s.startswith('"""') or s.startswith("'''"):
        return True
    # Imports
    if s.startswith("import ") or s.startswith("from ") or s.startswith("use ") or "require(" in s:
        return True
    # Type definitions / annotations
    if s.startswith("type ") or s.startswith("interface ") or s.startswith("typedef "):
        return True
    if TYPE_ANNOTATION_ONLY.match(s):
        return True
    # Log / print statements
    if s.startswith("print(") or s.startswith("console.log(") or s.startswith("console.error(") or s.startswith("console.warn("):
        return True
    if re.match(r"^(?:logger|logging|log|console)\.(?:debug|info|warning|warn|error|critical|exception|log|trace)\b", s):
        return True
    if re.match(r"^sys\.(?:stdout|stderr)\.write\(", s):
        return True
    return False


# ---------------------------------------------------------------------------
# Diff Hunk Candidate Extraction
# ---------------------------------------------------------------------------

def extract_diff_mutation_candidates(diff_text: str) -> List[MutationCandidate]:
    """
    Extracts candidate modified lines from a unified git diff text.
    Filters out non-code files, test files, arid lines, and pragma-marked lines.
    Tracks precise 1-indexed target line numbers in the new file.
    """
    candidates: List[MutationCandidate] = []
    current_file = ""
    current_line = 0
    in_hunk = False

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("+++ "):
            path_part = raw_line[4:].strip()
            if path_part.startswith("b/"):
                path_part = path_part[2:]
            current_file = path_part
            in_hunk = False
        elif raw_line.startswith("@@ "):
            match = re.search(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw_line)
            if match:
                current_line = int(match.group(1))
                in_hunk = True
            else:
                in_hunk = False
        elif in_hunk:
            ext = Path(current_file).suffix
            # Skip non-mutatable or test files
            if current_file and (ext not in MUTATABLE_EXTENSIONS or is_test_file(current_file)):
                if raw_line.startswith("+") and not raw_line.startswith("+++"):
                    current_line += 1
                elif raw_line.startswith(" "):
                    current_line += 1
                continue

            if raw_line.startswith("+") and not raw_line.startswith("+++"):
                content = raw_line[1:]
                if not is_arid_line(content) and not has_no_mutant_pragma(content):
                    candidates.append(MutationCandidate(
                        file_path=current_file,
                        line_number=current_line,
                        content=content,
                    ))
                current_line += 1
            elif raw_line.startswith(" "):
                current_line += 1
            elif raw_line.startswith("-"):
                pass

    return candidates


# ---------------------------------------------------------------------------
# Mutation Operators Engine
# ---------------------------------------------------------------------------

def apply_operator(src: str, operator: str) -> str:
    """
    Applies one of the 5-6 standard mutation operators to source code or line snippet:
    1. condition_inversion: == <-> !=, < <-> >=, is <-> is not, in <-> not in
    2. logical_swap: and <-> or, && <-> ||
    3. boundary_shift: x + 1 <-> x - 1, > 0 <-> >= 0, < 0 <-> <= 0
    4. return_stub: return x -> return None / False / True
    5. void_statement_delete: drop side-effect call -> pass
    6. literal_mutation: True <-> False
    """
    s = src

    if operator == "condition_inversion":
        # Order matters: replace longer keywords first
        if " is not " in s:
            return s.replace(" is not ", " is ", 1)
        if " is " in s:
            return s.replace(" is ", " is not ", 1)
        if " not in " in s:
            return s.replace(" not in ", " in ", 1)
        if " in " in s:
            return s.replace(" in ", " not in ", 1)
        if " != " in s:
            return s.replace(" != ", " == ", 1)
        if " == " in s:
            return s.replace(" == ", " != ", 1)
        if " >= " in s:
            return s.replace(" >= ", " < ", 1)
        if " <= " in s:
            return s.replace(" <= ", " > ", 1)
        if " > " in s:
            return s.replace(" > ", " <= ", 1)
        if " < " in s:
            return s.replace(" < ", " >= ", 1)
        if "if not " in s:
            return s.replace("if not ", "if ", 1)
        if re.search(r"\bnot\s+", s):
            return re.sub(r"\bnot\s+", "", s, count=1)

    elif operator == "logical_swap":
        if " and " in s:
            return s.replace(" and ", " or ", 1)
        if " or " in s:
            return s.replace(" or ", " and ", 1)
        if "&&" in s:
            return s.replace("&&", "||", 1)
        if "||" in s:
            return s.replace("||", "&&", 1)

    elif operator == "boundary_shift":
        if " += " in s:
            return s.replace(" += ", " -= ", 1)
        if " -= " in s:
            return s.replace(" -= ", " += ", 1)
        if " *= " in s:
            return s.replace(" *= ", " /= ", 1)
        if " /= " in s:
            return s.replace(" /= ", " *= ", 1)
        if " + 1" in s:
            return s.replace(" + 1", " - 1", 1)
        if " - 1" in s:
            return s.replace(" - 1", " + 1", 1)
        if " > 0" in s:
            return s.replace(" > 0", " >= 0", 1)
        if " < 0" in s:
            return s.replace(" < 0", " <= 0", 1)
        if " >= 0" in s:
            return s.replace(" >= 0", " > 0", 1)
        if " <= 0" in s:
            return s.replace(" <= 0", " < 0", 1)
        if " > " in s:
            return s.replace(" > ", " >= ", 1)
        if " < " in s:
            return s.replace(" < ", " <= ", 1)
        if " >= " in s:
            return s.replace(" >= ", " > ", 1)
        if " <= " in s:
            return s.replace(" <= ", " < ", 1)
        if " + " in s:
            return s.replace(" + ", " - ", 1)
        if " - " in s:
            return s.replace(" - ", " + ", 1)

    elif operator == "return_stub":
        m = re.match(r"^(\s*return)\s+(.+)$", s)
        if m:
            val = m.group(2).strip()
            if val == "True":
                return m.group(1) + " False"
            elif val == "False":
                return m.group(1) + " True"
            elif val == "None":
                return m.group(1) + " False"
            else:
                return m.group(1) + " None"
        if s.strip() == "return":
            return "return False"

    elif operator == "void_statement_delete":
        return "pass"

    elif operator == "literal_mutation":
        if "True" in s:
            return s.replace("True", "False", 1)
        if "False" in s:
            return s.replace("False", "True", 1)
        if "true" in s:
            return s.replace("true", "false", 1)
        if "false" in s:
            return s.replace("false", "true", 1)

    return s


class PythonAstMutator(ast.NodeTransformer):
    """
    Standard library ast.NodeTransformer that surgically mutates target nodes
    on target_line and records coordinate spans for non-destructive replacement.
    """
    def __init__(self, operator: str, target_line: Optional[int] = None):
        self.operator = operator
        self.target_line = target_line
        self.mutated = False
        self.span: Optional[Tuple[int, int, int, int]] = None
        self.replacement_text: Optional[str] = None

    def _matches_line(self, node: ast.AST) -> bool:
        if self.target_line is None:
            return True
        lineno = getattr(node, "lineno", None)
        if lineno is None:
            return False
        end_lineno = getattr(node, "end_lineno", None) or lineno
        return lineno <= self.target_line <= end_lineno

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        if not self.mutated and self._matches_line(node):
            if self.operator == "condition_inversion":
                new_ops = []
                for o in node.ops:
                    if isinstance(o, ast.Eq): new_ops.append(ast.NotEq())
                    elif isinstance(o, ast.NotEq): new_ops.append(ast.Eq())
                    elif isinstance(o, ast.Lt): new_ops.append(ast.GtE())
                    elif isinstance(o, ast.GtE): new_ops.append(ast.Lt())
                    elif isinstance(o, ast.Gt): new_ops.append(ast.LtE())
                    elif isinstance(o, ast.LtE): new_ops.append(ast.Gt())
                    elif isinstance(o, ast.Is): new_ops.append(ast.IsNot())
                    elif isinstance(o, ast.IsNot): new_ops.append(ast.Is())
                    elif isinstance(o, ast.In): new_ops.append(ast.NotIn())
                    elif isinstance(o, ast.NotIn): new_ops.append(ast.In())
                    else: new_ops.append(o)
                node.ops = new_ops
                self.mutated = True
                self.span = (node.lineno, node.col_offset, node.end_lineno or node.lineno, node.end_col_offset or (node.col_offset + 5))
                self.replacement_text = ast.unparse(node)
                return node
            elif self.operator == "boundary_shift":
                new_ops = []
                for o in node.ops:
                    if isinstance(o, ast.Gt): new_ops.append(ast.GtE())
                    elif isinstance(o, ast.GtE): new_ops.append(ast.Gt())
                    elif isinstance(o, ast.Lt): new_ops.append(ast.LtE())
                    elif isinstance(o, ast.LtE): new_ops.append(ast.Lt())
                    else: new_ops.append(o)
                node.ops = new_ops
                self.mutated = True
                self.span = (node.lineno, node.col_offset, node.end_lineno or node.lineno, node.end_col_offset or (node.col_offset + 5))
                self.replacement_text = ast.unparse(node)
                return node
        return self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        if not self.mutated and self._matches_line(node) and self.operator == "condition_inversion":
            if isinstance(node.op, ast.Not):
                self.mutated = True
                self.span = (node.lineno, node.col_offset, node.end_lineno or node.lineno, node.end_col_offset or (node.col_offset + 5))
                self.replacement_text = ast.unparse(node.operand)
                return node.operand
        return self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        if not self.mutated and self._matches_line(node) and self.operator == "logical_swap":
            if isinstance(node.op, ast.And): node.op = ast.Or()
            elif isinstance(node.op, ast.Or): node.op = ast.And()
            self.mutated = True
            self.span = (node.lineno, node.col_offset, node.end_lineno or node.lineno, node.end_col_offset or (node.col_offset + 5))
            self.replacement_text = ast.unparse(node)
            return node
        return self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        if not self.mutated and self._matches_line(node) and self.operator == "boundary_shift":
            if isinstance(node.op, ast.Add):
                node.op = ast.Sub()
                self.mutated = True
                self.span = (node.lineno, node.col_offset, node.end_lineno or node.lineno, node.end_col_offset or (node.col_offset + 5))
                self.replacement_text = ast.unparse(node)
                return node
            elif isinstance(node.op, ast.Sub):
                node.op = ast.Add()
                self.mutated = True
                self.span = (node.lineno, node.col_offset, node.end_lineno or node.lineno, node.end_col_offset or (node.col_offset + 5))
                self.replacement_text = ast.unparse(node)
                return node
        return self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> ast.AST:
        if not self.mutated and self._matches_line(node) and self.operator == "boundary_shift":
            if isinstance(node.op, ast.Add):
                node.op = ast.Sub()
                self.mutated = True
                self.span = (node.lineno, node.col_offset, node.end_lineno or node.lineno, node.end_col_offset or (node.col_offset + 5))
                self.replacement_text = ast.unparse(node)
                return node
            elif isinstance(node.op, ast.Sub):
                node.op = ast.Add()
                self.mutated = True
                self.span = (node.lineno, node.col_offset, node.end_lineno or node.lineno, node.end_col_offset or (node.col_offset + 5))
                self.replacement_text = ast.unparse(node)
                return node
            elif isinstance(node.op, ast.Mult):
                node.op = ast.Div()
                self.mutated = True
                self.span = (node.lineno, node.col_offset, node.end_lineno or node.lineno, node.end_col_offset or (node.col_offset + 5))
                self.replacement_text = ast.unparse(node)
                return node
            elif isinstance(node.op, (ast.Div, ast.FloorDiv)):
                node.op = ast.Mult()
                self.mutated = True
                self.span = (node.lineno, node.col_offset, node.end_lineno or node.lineno, node.end_col_offset or (node.col_offset + 5))
                self.replacement_text = ast.unparse(node)
                return node
        return self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> ast.AST:
        if not self.mutated and self._matches_line(node) and self.operator == "return_stub":
            if isinstance(node.value, ast.Constant) and type(node.value.value) is bool:
                node.value.value = not node.value.value
            elif node.value is None or (isinstance(node.value, ast.Constant) and node.value.value is None):
                node.value = ast.Constant(value=False)
            else:
                node.value = ast.Constant(value=None)
            self.mutated = True
            self.span = (node.lineno, node.col_offset, node.end_lineno or node.lineno, node.end_col_offset or (node.col_offset + 5))
            self.replacement_text = ast.unparse(node)
            return node
        return self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> ast.AST:
        if not self.mutated and self._matches_line(node) and self.operator == "void_statement_delete":
            if isinstance(node.value, ast.Call) or (isinstance(node.value, ast.Await) and isinstance(node.value.value, ast.Call)):
                self.mutated = True
                self.span = (node.lineno, node.col_offset, node.end_lineno or node.lineno, node.end_col_offset or (node.col_offset + 5))
                self.replacement_text = "pass"
                return ast.Pass()
        return self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if not self.mutated and self._matches_line(node) and self.operator == "literal_mutation":
            if type(node.value) is bool:
                node.value = not node.value
                self.mutated = True
                self.span = (node.lineno, node.col_offset, node.end_lineno or node.lineno, node.end_col_offset or (node.col_offset + 5))
                self.replacement_text = ast.unparse(node)
                return node
        return node


def mutate_python_source(src: str, target_line: int, operator: str) -> Tuple[str, str]:
    """
    Surgically mutates Python source code at 1-indexed target_line with operator.
    Uses AST NodeTransformer with coordinate-based surgical slicing to preserve
    comments, whitespace, and formatting across the file.
    Validates that the resulting code compiles with ast.parse.
    Returns (mutated_source, unified_diff_snippet).
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src, ""

    mutator = PythonAstMutator(operator=operator, target_line=target_line)
    mutator.visit(tree)

    lines = src.splitlines(keepends=True)
    if not mutator.mutated or not mutator.span or mutator.replacement_text is None:
        return src, ""

    start_l, start_c, end_l, end_c = mutator.span
    if start_l < 1 or start_l > len(lines) or end_l < 1 or end_l > len(lines) or start_l > end_l:
        return src, ""

    if start_l == end_l:
        line_bytes = lines[start_l - 1].encode("utf-8")
        prefix = line_bytes[:start_c].decode("utf-8", errors="replace")
        suffix = line_bytes[end_c:].decode("utf-8", errors="replace")
        new_line_text = prefix + mutator.replacement_text + suffix
        new_lines = list(lines[:start_l - 1]) + [new_line_text] + list(lines[end_l:])
    else:
        start_line_bytes = lines[start_l - 1].encode("utf-8")
        prefix = start_line_bytes[:start_c].decode("utf-8", errors="replace")
        end_line_bytes = lines[end_l - 1].encode("utf-8")
        suffix = end_line_bytes[end_c:].decode("utf-8", errors="replace")
        new_line_text = prefix + mutator.replacement_text + suffix
        new_lines = list(lines[:start_l - 1]) + [new_line_text] + list(lines[end_l:])

    mutated_src = "".join(new_lines)
    try:
        ast.parse(mutated_src)
    except SyntaxError:
        return src, ""

    diff = "".join(difflib.unified_diff(lines, mutated_src.splitlines(keepends=True), lineterm=""))
    return mutated_src, diff


def mutate_token_source(code: str, lang: str = "ts") -> Tuple[str, str]:
    """
    Polyglot token-level mutation fallback for TypeScript/JavaScript and Rust.
    Detects candidates and applies token swaps without external dependencies.
    Returns (mutated_code, operator_name).
    """
    replacements = [
        ("===", "!==", "condition_inversion"),
        ("!==", "===", "condition_inversion"),
        ("==", "!=", "condition_inversion"),
        ("!=", "==", "condition_inversion"),
        ("&&", "||", "logical_swap"),
        ("||", "&&", "logical_swap"),
        (" + 1", " - 1", "boundary_shift"),
        (" - 1", " + 1", "boundary_shift"),
        (" >= ", " < ", "condition_inversion"),
        (" <= ", " > ", "condition_inversion"),
        (" > 0", " >= 0", "boundary_shift"),
        (" < 0", " <= 0", "boundary_shift"),
        (" > ", " <= ", "condition_inversion"),
        (" < ", " >= ", "condition_inversion"),
    ]

    for token, repl, op in replacements:
        if token in code:
            return code.replace(token, repl, 1), op

    if re.search(r"\btrue\b", code):
        return re.sub(r"\btrue\b", "false", code, count=1), "literal_mutation"
    if re.search(r"\bfalse\b", code):
        return re.sub(r"\bfalse\b", "true", code, count=1), "literal_mutation"

    # Void call deletion in JS/TS/Rust: comment out call
    CONTROL_KEYWORDS = {"if", "while", "for", "switch", "catch", "function", "return"}
    if "=" not in code and "return" not in code:
        tokens_in_line = set(re.findall(r"\b[a-zA-Z_]\w*\b", code))
        if not (tokens_in_line & CONTROL_KEYWORDS):
            m = re.search(r"\b([a-zA-Z_]\w*)\s*\([^;)]*\);?", code)
            if m:
                mutated = re.sub(r"([a-zA-Z_]\w*\s*\([^;)]*\);?)", r"/* \1 */", code, count=1)
                if mutated != code and mutated.count("(") == mutated.count(")"):
                    return mutated, "void_statement_delete"

    return code, ""


# ---------------------------------------------------------------------------
# Diversity Sampling & Function Mutator
# ---------------------------------------------------------------------------

def generate_function_mutants(func_code: str, max_mutants: int = 6) -> List[FunctionMutant]:
    """
    Parses a Python function or code block and generates up to max_mutants (default 5-6)
    diverse mutants across condition inversion, logic swap, boundary shift, return stub,
    void statement delete, and literal mutation.
    """
    tree = ast.parse(func_code)
    func_name = ""
    by_op: Dict[str, List[Tuple[int, str]]] = {}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not func_name:
                func_name = node.name
        if not hasattr(node, "lineno"):
            continue

        line_num = node.lineno
        if isinstance(node, ast.Compare):
            by_op.setdefault("condition_inversion", []).append((line_num, "condition_inversion"))
            # If relational comparison, also candidate for boundary shift
            for op_node in node.ops:
                if isinstance(op_node, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
                    by_op.setdefault("boundary_shift", []).append((line_num, "boundary_shift"))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            by_op.setdefault("condition_inversion", []).append((line_num, "condition_inversion"))
        elif isinstance(node, ast.BoolOp):
            by_op.setdefault("logical_swap", []).append((line_num, "logical_swap"))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            by_op.setdefault("boundary_shift", []).append((line_num, "boundary_shift"))
        elif isinstance(node, ast.Return):
            by_op.setdefault("return_stub", []).append((line_num, "return_stub"))
        elif isinstance(node, ast.Expr) and (
            isinstance(node.value, ast.Call)
            or (isinstance(node.value, ast.Await) and isinstance(node.value.value, ast.Call))
        ):
            by_op.setdefault("void_statement_delete", []).append((line_num, "void_statement_delete"))
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            by_op.setdefault("literal_mutation", []).append((line_num, "literal_mutation"))

    # Diversity selection: round-robin across available operators
    selected: List[Tuple[int, str]] = []
    ops_list = list(by_op.keys())
    idx = 0
    max_loops = 100
    while len(selected) < max_mutants and any(by_op.values()) and max_loops > 0:
        max_loops -= 1
        op = ops_list[idx % len(ops_list)]
        idx += 1
        if by_op.get(op):
            cand = by_op[op].pop(0)
            if cand not in selected:
                selected.append(cand)

    mutants: List[FunctionMutant] = []
    for l, op in selected:
        mut_src, diff = mutate_python_source(func_code, l, op)
        if mut_src and mut_src != func_code:
            mutants.append(FunctionMutant(
                mutated_code=mut_src,
                operator=op,
                line_number=l,
                diff_snippet=diff,
                function_name=func_name,
            ))

    return mutants


# ---------------------------------------------------------------------------
# Runner & Verification Orchestration
# ---------------------------------------------------------------------------

def run_micro_mutation(
    target_diff: Optional[str] = None,
    files: Optional[List[str]] = None,
    config: Optional[MutationConfig] = None,
) -> MutationResult:
    """
    Executes diff-aware in-harness micro-mutation testing against uncommitted diffs.
    Runs affected test suites for each mutant and reports surviving mutants.
    Guarantees hermetic in-memory backups and zero source corruption.
    """
    _install_safety_handlers()
    cfg = config or MutationConfig()
    repo_root = cfg.repo_root or Path.cwd().resolve()

    # 1. Diff Extraction
    if target_diff is not None:
        diff_text = target_diff
    else:
        try:
            res = subprocess.run(
                ["git", "diff", "-U0", "HEAD"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            diff_text = res.stdout if res.returncode == 0 else ""
        except Exception:
            diff_text = ""

    # 2. Fast Path: Clean working tree
    if not diff_text.strip() and not files:
        return MutationResult(total_mutants=0, killed_mutants=0, survived_mutants=[], exit_code=0)

    # 3. Candidate Discovery
    candidates = extract_diff_mutation_candidates(diff_text)
    if files:
        file_set = {str(Path(f).resolve()) for f in files} | {str(f) for f in files}
        candidates = [c for c in candidates if str((repo_root / c.file_path).resolve()) in file_set or c.file_path in file_set]

    if not candidates:
        return MutationResult(total_mutants=0, killed_mutants=0, survived_mutants=[], exit_code=0)

    # 4. Group by file
    by_file: Dict[str, List[MutationCandidate]] = {}
    for c in candidates:
        by_file.setdefault(c.file_path, []).append(c)

    total_mutants = 0
    killed_mutants = 0
    survived_mutants: List[SurvivingMutant] = []
    suppressed_by_pragma = 0

    # 5. Process each file
    for rel_path, file_candidates in by_file.items():
        if total_mutants >= cfg.max_mutants_total:
            break
        file_path = repo_root / rel_path
        if not file_path.is_file():
            continue

        try:
            original_content = file_path.read_text(encoding="utf-8")
        except Exception:
            continue

        lines = original_content.splitlines()

        # Check line-level escape pragmas (same line or preceding line)
        active_candidates: List[MutationCandidate] = []
        for cand in file_candidates:
            line_idx = cand.line_number - 1
            if line_idx < 0 or line_idx >= len(lines):
                continue
            line_text = lines[line_idx]

            # Same line pragma
            if has_no_mutant_pragma(line_text):
                suppressed_by_pragma += 1
                continue

            # Preceding line pragma
            if line_idx > 0 and has_no_mutant_pragma(lines[line_idx - 1]):
                suppressed_by_pragma += 1
                continue

            active_candidates.append(cand)

        if not active_candidates:
            continue

        # Backup file in memory
        ACTIVE_BACKUPS[file_path] = original_content

        # Generate planned mutants
        is_python = rel_path.endswith(".py")
        planned_mutants: List[FunctionMutant] = []

        if is_python:
            target_lines = {c.line_number for c in active_candidates}
            # Walk AST to locate functions and candidates
            try:
                tree = ast.parse(original_content)
                # Map each target line to enclosing function name
                func_map: Dict[int, str] = {}
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        start_l = node.lineno
                        end_l = getattr(node, "end_lineno", start_l + len(node.body))
                        for l in range(start_l, end_l + 1):
                            if l in target_lines:
                                func_map[l] = node.name

                # Try operators on target lines
                cands_by_func: Dict[str, List[Tuple[int, str]]] = {}
                for cand in active_candidates:
                    l = cand.line_number
                    fname = func_map.get(l, "<module>")
                    for op in ("condition_inversion", "logical_swap", "boundary_shift", "return_stub", "void_statement_delete", "literal_mutation"):
                        cands_by_func.setdefault(fname, []).append((l, op))

                for fname, op_cands in cands_by_func.items():
                    # Diversity sample per function: cap at max_mutants_per_function
                    count = 0
                    seen_ops: Set[str] = set()
                    for l, op in op_cands:
                        if count >= cfg.max_mutants_per_function:
                            break
                        if op in seen_ops:
                            continue
                        file_mut_src, diff_snip = mutate_python_source(
                            original_content,
                            target_line=l,
                            operator=op,
                        )
                        if file_mut_src and file_mut_src != original_content:
                            planned_mutants.append(FunctionMutant(
                                mutated_code=file_mut_src,
                                operator=op,
                                line_number=l,
                                diff_snippet=diff_snip,
                                function_name=fname,
                            ))
                            seen_ops.add(op)
                            count += 1
            except Exception:
                pass
        else:
            # Polyglot TS/JS/Rust fallback
            for cand in active_candidates:
                mut_line, op = mutate_token_source(cand.content, lang=Path(rel_path).suffix.lstrip("."))
                if mut_line != cand.content:
                    file_lines = list(lines)
                    file_lines[cand.line_number - 1] = mut_line
                    file_mut_src = "\n".join(file_lines) + ("\n" if original_content.endswith("\n") else "")
                    diff_snip = f"- {cand.content}\n+ {mut_line}"
                    planned_mutants.append(FunctionMutant(
                        mutated_code=file_mut_src,
                        operator=op,
                        line_number=cand.line_number,
                        diff_snippet=diff_snip,
                        function_name="<external>",
                    ))

        # Run planned mutants
        for pm in planned_mutants:
            if total_mutants >= cfg.max_mutants_total:
                break
            total_mutants += 1
            file_path.write_text(pm.mutated_code, encoding="utf-8")
            try:
                resolved = resolve_affected_tests(
                    repo_root=repo_root,
                    modified_files=[rel_path],
                    mode="diff",
                )
                if rel_path == "harness/cli.py" and "tests/test_cli.py" in resolved.runner_cmd:
                    extra_cli_tests = [
                        t for t in ("tests/test_test_smells.py", "tests/test_micro_probe.py")
                        if (repo_root / t).is_file()
                    ]
                    if extra_cli_tests:
                        resolved.runner_cmd += " " + " ".join(extra_cli_tests)

                if resolved.is_empty:
                    survived_mutants.append(SurvivingMutant(
                        file_path=rel_path,
                        function_name=pm.function_name,
                        line_number=pm.line_number,
                        operator=pm.operator,
                        diff_snippet=pm.diff_snippet,
                        test_target="<none>",
                    ))
                else:
                    clean_cmd, guarded_env = inject_non_interactive_guards(resolved.runner_cmd)
                    if "PYTHONPATH" not in guarded_env or str(repo_root) not in guarded_env.get("PYTHONPATH", ""):
                        guarded_env["PYTHONPATH"] = f"{repo_root}:{guarded_env.get('PYTHONPATH', '')}".rstrip(":")
                    try:
                        proc = subprocess.run(
                            clean_cmd,
                            shell=True,
                            env=guarded_env,
                            cwd=str(repo_root),
                            capture_output=True,
                            text=True,
                            timeout=cfg.timeout_sec,
                        )
                        if proc.returncode != 0:
                            killed_mutants += 1
                        else:
                            survived_mutants.append(SurvivingMutant(
                                file_path=rel_path,
                                function_name=pm.function_name,
                                line_number=pm.line_number,
                                operator=pm.operator,
                                diff_snippet=pm.diff_snippet,
                                test_target=resolved.runner_cmd,
                            ))
                            if cfg.fail_fast:
                                break
                    except subprocess.TimeoutExpired:
                        killed_mutants += 1
            finally:
                file_path.write_text(original_content, encoding="utf-8")

        ACTIVE_BACKUPS.pop(file_path, None)

    exit_code = 1 if len(survived_mutants) > 0 else 0
    return MutationResult(
        total_mutants=total_mutants,
        killed_mutants=killed_mutants,
        survived_mutants=survived_mutants,
        exit_code=exit_code,
        suppressed_by_pragma=suppressed_by_pragma,
    )


# ===========================================================================
# Route A Compatibility Shims (RFC-051 Phase 3.1)
# ===========================================================================

@dataclass
class Mutant:
    mutant_id: str
    file_path: Path
    function_name: str
    line_number: int
    operator: str
    original_source: str
    mutated_source: str
    diff: str
    status: str = "pending"  # "pending" | "killed" | "survived" | "error"
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mutant_id": self.mutant_id,
            "file_path": str(self.file_path),
            "function_name": self.function_name,
            "line_number": self.line_number,
            "operator": self.operator,
            "diff": self.diff,
            "status": self.status,
            "error_message": self.error_message,
        }


@dataclass
class MutationReport:
    total_mutants: int
    killed: int
    survived: int
    errors: int
    score: float
    surviving_mutants: List[Mutant] = field(default_factory=list)
    passed: bool = True
    report_text: str = ""
    ecosystem_tool: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_mutants": self.total_mutants,
            "killed": self.killed,
            "survived": self.survived,
            "errors": self.errors,
            "score": round(self.score, 2),
            "passed": self.passed,
            "ecosystem_tool": self.ecosystem_tool,
            "surviving_mutants": [m.to_dict() for m in self.surviving_mutants],
        }


def _replace_source_segment(
    source: str,
    lineno: int,
    col_offset: int,
    end_lineno: int,
    end_col_offset: int,
    replacement: str,
) -> str:
    """Replaces an exact character segment in the source without modifying other lines."""
    lines = source.splitlines(keepends=True)
    if not (1 <= lineno <= len(lines)) or not (1 <= end_lineno <= len(lines)):
        return source

    if lineno == end_lineno:
        line = lines[lineno - 1]
        lines[lineno - 1] = line[:col_offset] + replacement + line[end_col_offset:]
    else:
        start_line = lines[lineno - 1][:col_offset]
        end_line = lines[end_lineno - 1][end_col_offset:]
        lines[lineno - 1] = start_line + replacement + end_line
        del lines[lineno:end_lineno]

    return "".join(lines)


def _compute_unified_diff(original: str, mutated: str, file_path: str) -> str:
    """Computes a clean unified diff between original and mutated source."""
    diff_lines = difflib.unified_diff(
        original.splitlines(keepends=True),
        mutated.splitlines(keepends=True),
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=2,
    )
    return "".join(diff_lines)


def parse_diff_lines(diff_text: str) -> Dict[str, Set[int]]:
    """
    Parses unified diff text to extract modified line numbers per file.
    Returns mapping from relative file path to set of modified 1-indexed line numbers.
    """
    modified_lines: Dict[str, Set[int]] = {}
    current_file: Optional[str] = None
    current_line = 0

    diff_file_pat = re.compile(r"^diff --git a/(.+?) b/(.+?)$")
    hunk_pat = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    for line in diff_text.splitlines():
        m_file = diff_file_pat.match(line)
        if m_file:
            current_file = m_file.group(2)
            if current_file not in modified_lines:
                modified_lines[current_file] = set()
            continue

        if line.startswith("+++ "):
            path_part = line[4:].strip()
            if path_part.startswith("b/"):
                path_part = path_part[2:]
            if path_part and path_part != "/dev/null":
                current_file = path_part
                if current_file not in modified_lines:
                    modified_lines[current_file] = set()
            continue

        m_hunk = hunk_pat.match(line)
        if m_hunk:
            current_line = int(m_hunk.group(1))
            continue

        if current_file is not None and "current_line" in locals():
            if line.startswith("+") and not line.startswith("+++"):
                modified_lines[current_file].add(current_line)
                current_line += 1
            elif line.startswith(" "):
                current_line += 1
            elif line.startswith("-"):
                pass

    return modified_lines


def detect_ecosystem_tools(repo_root: Path) -> Optional[str]:
    """Detects external mutation test runners configured in the repository."""
    repo_root = Path(repo_root)
    if (
        (repo_root / "stryker.config.json").is_file()
        or (repo_root / "stryker.conf.json").is_file()
        or (repo_root / "stryker.config.mjs").is_file()
    ):
        return "stryker"
    if (
        (repo_root / "cargo-mutants.toml").is_file()
        or (repo_root / ".cargo/mutants.toml").is_file()
    ):
        return "cargo-mutants"
    return None


class FunctionMutationCollector(ast.NodeVisitor):
    """AST Visitor collecting candidate AST nodes for mutation in a function."""

    def __init__(self, target_lines: Set[int], source_lines: List[str]):
        self.target_lines = target_lines
        self.source_lines = source_lines

        self.comparisons: List[ast.Compare] = []
        self.binops: List[ast.BinOp] = []
        self.augassigns: List[ast.AugAssign] = []
        self.boolops: List[ast.BoolOp] = []
        self.not_unaryops: List[ast.UnaryOp] = []
        self.statements: List[ast.stmt] = []
        self.returns: List[ast.Return] = []

    def _line_in_target(self, node: ast.AST) -> bool:
        lineno = getattr(node, "lineno", -1)
        if lineno in self.target_lines:
            if 1 <= lineno <= len(self.source_lines):
                line_str = self.source_lines[lineno - 1]
                if has_no_mutant_pragma(line_str) or is_arid_line(line_str):
                    return False
            return True
        return False

    def visit_Compare(self, node: ast.Compare) -> None:
        if self._line_in_target(node):
            self.comparisons.append(node)
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if self._line_in_target(node):
            self.binops.append(node)
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        if self._line_in_target(node):
            self.boolops.append(node)
        self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        if isinstance(node.op, ast.Not) and self._line_in_target(node):
            self.not_unaryops.append(node)
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        if self._line_in_target(node):
            self.returns.append(node)
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> None:
        if self._line_in_target(node):
            self.statements.append(node)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._line_in_target(node):
            self.statements.append(node)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if self._line_in_target(node):
            self.augassigns.append(node)
            self.statements.append(node)
        self.generic_visit(node)


def generate_mutants_for_function(
    file_path: Path,
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    source_code: str,
    source_lines: List[str],
    target_lines: Set[int],
    mutant_counter: List[int],
) -> List[Mutant]:
    """Generates 5-6 mutants for a modified function using the 5 operators."""
    collector = FunctionMutationCollector(target_lines, source_lines)
    collector.visit(func_node)

    mutants: List[Mutant] = []
    func_name = func_node.name

    def _add_mutant(node: ast.AST, operator: str, replacement: str) -> None:
        mutant_counter[0] += 1
        m_id = f"mutant_{mutant_counter[0]}"
        lineno = getattr(node, "lineno", 1)
        col_offset = getattr(node, "col_offset", 0)
        end_lineno = getattr(node, "end_lineno", lineno)
        end_col_offset = getattr(node, "end_col_offset", col_offset + len(replacement))

        mutated_src = _replace_source_segment(
            source=source_code,
            lineno=lineno,
            col_offset=col_offset,
            end_lineno=end_lineno,
            end_col_offset=end_col_offset,
            replacement=replacement,
        )
        diff_str = _compute_unified_diff(source_code, mutated_src, str(file_path))

        mutants.append(
            Mutant(
                mutant_id=m_id,
                file_path=file_path,
                function_name=func_name,
                line_number=lineno,
                operator=operator,
                original_source=source_code,
                mutated_source=mutated_src,
                diff=diff_str,
            )
        )

    # 1. Condition Inversion: == <-> !=, < <-> >=, <= <-> >, in <-> not in, is <-> is not
    if collector.comparisons:
        cmp_node = collector.comparisons[0]
        if len(cmp_node.ops) == 1:
            op = cmp_node.ops[0]
            new_op: Optional[ast.cmpop] = None
            if isinstance(op, ast.Eq):
                new_op = ast.NotEq()
            elif isinstance(op, ast.NotEq):
                new_op = ast.Eq()
            elif isinstance(op, ast.Lt):
                new_op = ast.GtE()
            elif isinstance(op, ast.GtE):
                new_op = ast.Lt()
            elif isinstance(op, ast.LtE):
                new_op = ast.Gt()
            elif isinstance(op, ast.Gt):
                new_op = ast.LtE()
            elif isinstance(op, ast.In):
                new_op = ast.NotIn()
            elif isinstance(op, ast.NotIn):
                new_op = ast.In()
            elif isinstance(op, ast.Is):
                new_op = ast.IsNot()
            elif isinstance(op, ast.IsNot):
                new_op = ast.Is()

            if new_op is not None:
                mutated_cmp = copy.deepcopy(cmp_node)
                mutated_cmp.ops = [new_op]
                _add_mutant(cmp_node, "condition_inversion", ast.unparse(mutated_cmp))

    # 2. Boundary Shift: + 1 <-> - 1, + <-> -, * <-> /
    if collector.binops:
        binop = collector.binops[0]
        new_op_bin: Optional[ast.operator] = None
        if isinstance(binop.op, ast.Add):
            new_op_bin = ast.Sub()
        elif isinstance(binop.op, ast.Sub):
            new_op_bin = ast.Add()
        elif isinstance(binop.op, ast.Mult):
            new_op_bin = ast.Div()
        elif isinstance(binop.op, (ast.Div, ast.FloorDiv)):
            new_op_bin = ast.Mult()

        if new_op_bin is not None:
            mutated_bin = copy.deepcopy(binop)
            mutated_bin.op = new_op_bin
            _add_mutant(binop, "boundary_shift", ast.unparse(mutated_bin))
    elif collector.augassigns:
        aug = collector.augassigns[0]
        new_op_aug: Optional[ast.operator] = None
        if isinstance(aug.op, ast.Add):
            new_op_aug = ast.Sub()
        elif isinstance(aug.op, ast.Sub):
            new_op_aug = ast.Add()
        elif isinstance(aug.op, ast.Mult):
            new_op_aug = ast.Div()
        elif isinstance(aug.op, (ast.Div, ast.FloorDiv)):
            new_op_aug = ast.Mult()

        if new_op_aug is not None:
            mutated_aug = copy.deepcopy(aug)
            mutated_aug.op = new_op_aug
            _add_mutant(aug, "boundary_shift", ast.unparse(mutated_aug))

    # 3. Logical Flip: and <-> or, not x <-> x
    if collector.boolops:
        boolop = collector.boolops[0]
        new_op_bool: Optional[ast.boolop] = None
        if isinstance(boolop.op, ast.And):
            new_op_bool = ast.Or()
        elif isinstance(boolop.op, ast.Or):
            new_op_bool = ast.And()

        if new_op_bool is not None:
            mutated_bop = copy.deepcopy(boolop)
            mutated_bop.op = new_op_bool
            _add_mutant(boolop, "logical_flip", ast.unparse(mutated_bop))
    elif collector.not_unaryops:
        unop = collector.not_unaryops[0]
        _add_mutant(unop, "logical_flip", ast.unparse(unop.operand))

    # 4. Statement Drop: Replace statement with pass
    if collector.statements:
        stmt = collector.statements[0]
        _add_mutant(stmt, "statement_drop", "pass")

    # 5. Return Negation / Replacement: return x -> return None, return True -> return False
    if collector.returns:
        ret_stmt = collector.returns[0]
        if ret_stmt.value is None or (isinstance(ret_stmt.value, ast.Constant) and ret_stmt.value.value is None):
            _add_mutant(ret_stmt, "return_negation", "return True")
        elif isinstance(ret_stmt.value, ast.Constant) and isinstance(ret_stmt.value.value, bool):
            new_val = not ret_stmt.value.value
            _add_mutant(ret_stmt, "return_negation", f"return {new_val}")
        else:
            _add_mutant(ret_stmt, "return_negation", "return None")

    return mutants


def generate_mutants_for_file(
    file_path: Path,
    target_lines: Set[int],
    mutant_counter: List[int],
) -> List[Mutant]:
    """Generates mutants for a single Python file across its modified functions."""
    if not file_path.is_file() or file_path.suffix.lower() not in (".py", ".pyi"):
        return []

    try:
        source_code = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source_code, filename=str(file_path))
    except Exception:
        return []

    source_lines = source_code.splitlines(keepends=True)
    mutants: List[Mutant] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_start = node.lineno
            fn_end = getattr(node, "end_lineno", fn_start + len(node.body))
            fn_lines = {ln for ln in target_lines if fn_start <= ln <= fn_end}
            if fn_lines:
                fn_mutants = generate_mutants_for_function(
                    file_path=file_path,
                    func_node=node,
                    source_code=source_code,
                    source_lines=source_lines,
                    target_lines=fn_lines,
                    mutant_counter=mutant_counter,
                )
                mutants.extend(fn_mutants)

    return mutants


def generate_mutants_for_diff(
    repo_root: Path,
    diff_text: Optional[str] = None,
) -> List[Mutant]:
    """
    Diff-aware mutant generator (Route A compatibility).
    """
    repo_root = Path(repo_root).resolve()
    if diff_text is not None:
        diff_lines_map = parse_diff_lines(diff_text)
    else:
        # Fallback to working tree git diff
        try:
            res = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
            diff_lines_map = parse_diff_lines(res.stdout) if res.stdout else {}
        except Exception:
            diff_lines_map = {}

    mutants: List[Mutant] = []
    mutant_counter = [0]

    for rel_path, line_set in diff_lines_map.items():
        if not line_set:
            continue
        file_path = (repo_root / rel_path).resolve()
        if not file_path.exists():
            continue
        if file_path.suffix.lower() in (".py", ".pyi"):
            if is_test_file(rel_path):
                continue
            file_mutants = generate_mutants_for_file(file_path, line_set, mutant_counter)
            mutants.extend(file_mutants)

    return mutants


def run_micro_mutation_probe(
    repo_root: Path,
    diff_text: Optional[str] = None,
    test_cmd: Optional[str] = None,
) -> MutationReport:
    """
    Runs diff-aware micro-mutation probe against modified lines in repository.
    (Route A compatibility entrypoint).
    """
    repo_root = Path(repo_root).resolve()
    ecosystem_tool = detect_ecosystem_tools(repo_root)

    mutants = generate_mutants_for_diff(repo_root, diff_text=diff_text)
    mutants = mutants[:20]

    if not mutants:
        return MutationReport(
            total_mutants=0,
            killed=0,
            survived=0,
            errors=0,
            score=100.0,
            passed=True,
            ecosystem_tool=ecosystem_tool,
            report_text="✔ 0 mutants generated for current diff (clean working tree or arid lines). Mutation score: 100.0%.",
        )

    actual_test_cmd = test_cmd
    if not actual_test_cmd:
        if (repo_root / "tests").is_dir():
            actual_test_cmd = "python3 -m unittest discover -s tests"
        else:
            actual_test_cmd = "python3 -m unittest"

    killed = 0
    survived = 0
    errors = 0
    surviving_mutants: List[Mutant] = []

    for mutant in mutants:
        original_content = mutant.file_path.read_text(encoding="utf-8")
        try:
            mutant.file_path.write_text(mutant.mutated_source, encoding="utf-8")
            res = subprocess.run(
                actual_test_cmd,
                shell=True,
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=3.0,
            )
            if res.returncode != 0:
                mutant.status = "killed"
                killed += 1
            else:
                mutant.status = "survived"
                survived += 1
                surviving_mutants.append(mutant)
        except subprocess.TimeoutExpired:
            mutant.status = "killed"
            killed += 1
        except Exception as ex:
            mutant.status = "error"
            mutant.error_message = str(ex)
            errors += 1
        finally:
            mutant.file_path.write_text(original_content, encoding="utf-8")

    total = len(mutants)
    score = (killed / total) * 100.0 if total > 0 else 100.0
    passed = (survived == 0)

    lines: List[str] = [
        f"Micro-Mutation Probe: {total} mutants generated across diff.",
        f"Killed: {killed} | Survived: {survived} | Errors: {errors} | Score: {score:.1f}%",
    ]
    if ecosystem_tool:
        lines.append(f"Ecosystem Mutation Runner Detected: {ecosystem_tool}")

    if surviving_mutants:
        lines.append("\n✖ SURVIVING MUTANTS DETECTED (Insufficient Test Coverage):")
        for sm in surviving_mutants:
            lines.append(f"\n--- [{sm.mutant_id}] {sm.file_path}:{sm.line_number} in {sm.function_name}() ({sm.operator}) ---")
            lines.append(sm.diff.strip())
        lines.append(
            "\nTip: Add assertions for these code paths, or annotate intentional exclusions with "
            "'# agyis: no-mutant <reason>'."
        )
    else:
        lines.append("\n✔ All mutants killed! Diff verification passed.")

    report_text = "\n".join(lines)

    return MutationReport(
        total_mutants=total,
        killed=killed,
        survived=survived,
        errors=errors,
        score=score,
        surviving_mutants=surviving_mutants,
        passed=passed,
        report_text=report_text,
        ecosystem_tool=ecosystem_tool,
    )
