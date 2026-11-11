# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Crash-safety handlers, mutation data models, and AST/token mutation operators."""

from __future__ import annotations

import ast
import atexit
from dataclasses import dataclass, field
import difflib
from pathlib import Path
import re
import signal
import sys
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

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
    error_message: Optional[str] = None


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


def replace_source_segment_utf8(
    source: str,
    lineno: int,
    col_offset: int,
    end_lineno: int,
    end_col_offset: int,
    replacement: str,
) -> str:
    """Replaces an AST segment using UTF-8 byte offsets without corrupting non-ASCII lines."""
    lines = source.splitlines(keepends=True)
    if lineno < 1 or lineno > len(lines) or end_lineno < 1 or end_lineno > len(lines) or lineno > end_lineno:
        return source
    if lineno == end_lineno:
        line_bytes = lines[lineno - 1].encode("utf-8")
        prefix = line_bytes[:col_offset].decode("utf-8", errors="replace")
        suffix = line_bytes[end_col_offset:].decode("utf-8", errors="replace")
    else:
        prefix = lines[lineno - 1].encode("utf-8")[:col_offset].decode("utf-8", errors="replace")
        suffix = lines[end_lineno - 1].encode("utf-8")[end_col_offset:].decode("utf-8", errors="replace")
    new_lines = list(lines[:lineno - 1]) + [prefix + replacement + suffix] + list(lines[end_lineno:])
    return "".join(new_lines)


def invert_compare_op(op: ast.cmpop) -> Optional[ast.cmpop]:
    """Returns the canonical negated AST comparison operator, or None if unsupported."""
    pairs = (
        (ast.Eq, ast.NotEq), (ast.NotEq, ast.Eq),
        (ast.Lt, ast.GtE), (ast.GtE, ast.Lt),
        (ast.Gt, ast.LtE), (ast.LtE, ast.Gt),
        (ast.Is, ast.IsNot), (ast.IsNot, ast.Is),
        (ast.In, ast.NotIn), (ast.NotIn, ast.In),
    )
    for src_t, dst_t in pairs:
        if isinstance(op, src_t):
            return dst_t()
    return None


def swap_arith_op(op: ast.operator, include_mult_div: bool = True) -> Optional[ast.operator]:
    """Returns the canonical swapped AST binary/augassign arithmetic operator."""
    if isinstance(op, ast.Add):
        return ast.Sub()
    if isinstance(op, ast.Sub):
        return ast.Add()
    if include_mult_div:
        if isinstance(op, ast.Mult):
            return ast.Div()
        if isinstance(op, (ast.Div, ast.FloorDiv)):
            return ast.Mult()
    return None


def flip_bool_op(op: ast.boolop) -> Optional[ast.boolop]:
    """Returns the canonical inverted AST boolean operator (and <-> or)."""
    if isinstance(op, ast.And):
        return ast.Or()
    if isinstance(op, ast.Or):
        return ast.And()
    return None


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
                new_ops = [invert_compare_op(o) or o for o in node.ops]
                node.ops = new_ops
                self.mutated = True
                self.span = (node.lineno, node.col_offset, node.end_lineno or node.lineno, node.end_col_offset or (node.col_offset + 5))
                self.replacement_text = ast.unparse(node)
                return node
            elif self.operator == "boundary_shift":
                new_ops = []
                for o in node.ops:
                    if isinstance(o, (ast.Gt, ast.GtE, ast.Lt, ast.LtE)):
                        if isinstance(o, ast.Gt): new_ops.append(ast.GtE())
                        elif isinstance(o, ast.GtE): new_ops.append(ast.Gt())
                        elif isinstance(o, ast.Lt): new_ops.append(ast.LtE())
                        else: new_ops.append(ast.Lt())
                    else:
                        new_ops.append(o)
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
            new_op = flip_bool_op(node.op)
            if new_op is not None:
                node.op = new_op
            self.mutated = True
            self.span = (node.lineno, node.col_offset, node.end_lineno or node.lineno, node.end_col_offset or (node.col_offset + 5))
            self.replacement_text = ast.unparse(node)
            return node
        return self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        if not self.mutated and self._matches_line(node) and self.operator == "boundary_shift":
            new_op = swap_arith_op(node.op, include_mult_div=False)
            if new_op is not None:
                node.op = new_op
                self.mutated = True
                self.span = (node.lineno, node.col_offset, node.end_lineno or node.lineno, node.end_col_offset or (node.col_offset + 5))
                self.replacement_text = ast.unparse(node)
                return node
        return self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> ast.AST:
        if not self.mutated and self._matches_line(node) and self.operator == "boundary_shift":
            new_op = swap_arith_op(node.op, include_mult_div=True)
            if new_op is not None:
                node.op = new_op
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
    mutated_src = replace_source_segment_utf8(src, start_l, start_c, end_l, end_c, mutator.replacement_text)
    if mutated_src == src:
        return src, ""
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
        elif isinstance(node, (ast.BinOp, ast.AugAssign)) and isinstance(node.op, (ast.Add, ast.Sub)):
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

